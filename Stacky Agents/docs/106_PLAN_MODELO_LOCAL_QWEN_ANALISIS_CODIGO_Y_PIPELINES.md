# Plan 106 — Modelo local Qwen 3 para análisis de código y creación de pipelines

**Estado:** CRITICADO v1 → v2 (RECHAZADO en v1; v2 corrige los bloqueantes)
**Fecha:** 2026-07-08 (v1 propuesto y criticado el mismo día)
**Dependencias:** planes 40-46 (runtimes), 71 (CI providers agnósticos), 87-91 (serie DevOps), 97 (presets por stack)
**No depende de:** planes 93-96, 98-105

## Changelog v1 → v2 (crítica adversarial)

- **C1 (BLOQUEANTE, diseño roto):** en v1 los endpoints `/api/llm/*` llamaban `copilot_bridge.invoke()`, que despacha por `config.LLM_BACKEND` global; con el backend normal (`copilot`) las requests iban a GitHub, NO a Qwen — KPI-2/KPI-3 eran falsos. Peor: para que funcionaran había que poner `LLM_BACKEND=local_llm` global, redirigiendo TODO el tráfico del bridge al modelo local (degradación masiva). v2: los endpoints llaman una función pública nueva `invoke_local_llm()` que va SIEMPRE al endpoint local, sin depender del backend global. El modo `LLM_BACKEND=local_llm` queda como opción avanzada separada (F2) con advertencia explícita.
- **C2 (BLOQUEANTE, crash garantizado):** v1 creaba `AgentExecution(ticket_id=None, ...)` — `ticket_id` es `nullable=False` (`models.py:211`) y faltaban los NOT NULL `input_context_json` (`models.py:215`) y `started_by` (`models.py:222`) → IntegrityError en el flush. v2: patrón de ticket interno discriminador `ado_id=-5` con `external_id` negativo único, copiado del precedente real `api/devops_agent.py:63-75`, y todos los NOT NULL seteados.
- **C3 (BLOQUEANTE, firma inventada):** `LogFn = Callable[[str, str], None]` (`copilot_bridge.py:120`) recibe `(level, msg)`; v1 llamaba `on_log(execution_id, "info", ...)` y pasaba `lambda eid, level, msg: None` → TypeError en runtime. v2: firma correcta en todos los snippets.
- **C4 (BLOQUEANTE, FlagSpec inventado):** v1 usaba `requires=[]` (el campo real es `str | None`, `harness_flags.py:30`) y `group="experimental"` (los valores reales son `"claude_code_cli" | "global"`, `harness_flags.py:26`); el test F0 exigía `requires==[]`, imposible. v2: FlagSpec con los campos reales.
- **C5 (BLOQUEANTE, paridad falsa):** KPI-4 v1 prometía que "los 3 runtimes usan el modelo local vía model_override" — falso: Claude Code CLI y Codex CLI spawnan binarios propios que jamás hablan con Ollama; `LLM_BACKEND` solo aplica al camino `copilot_bridge`. v2 reencuadra la paridad: la capacidad son endpoints HTTP backend-side, runtime-agnósticos por construcción (cualquier runtime/UI los consume); no se promete selección del modelo local dentro de los 3 CLIs.
- **C6 (IMPORTANTE, snippets con bugs):** `from __future__ annotations` (faltaba `import`); `@bp.post(..., methods=["POST"])` (Flask lanza TypeError si pasás `methods` al shortcut `.post`); `json.dumps` usado antes del `import json` local (NameError); `raw[:500]` sobre un dict (TypeError). Todos corregidos en v2.
- **C7 (IMPORTANTE, riel de UI):** v1 configuraba endpoint/modelo SOLO por env vars, violando el riel "toda config del operador va por UI". v2: `LOCAL_LLM_ENDPOINT`, `LOCAL_LLM_MODEL` y `LOCAL_LLM_TIMEOUT_SEC` se registran como FlagSpec `type="str"`/`"int"` (el tipo str ya existe: `harness_flags.py:2203`) con `requires="LOCAL_LLM_ENABLED"`, editables desde HarnessFlagsPanel.
- **C8 (IMPORTANTE, timeout irreal):** 30s hardcodeados matan cualquier análisis real con Qwen 32B q4 local (contextos grandes tardan minutos). v2: `LOCAL_LLM_TIMEOUT_SEC` configurable, default 120, min 10 / max 600.
- **C9 (IMPORTANTE, ruta fantasma):** `api/health.py` no existe; health vive en `api/diag.py`. Eliminada la frase vaga "(o el endpoint de health existente)".
- **C10 (IMPORTANTE, sin consumidor UI):** v1 dejaba los endpoints "para probar con curl/Postman" (trabajo manual del operador) y apuntaba a `frontend/src/pages/HarnessFlagsPanel.tsx` (está en `components/`). v2: F5 agrega un consumidor UI real mínimo (botón "Sugerir con IA local" en PipelineBuilderSection que pre-rellena campos editables — HITL).
- **C11 (MENOR):** `_ANALYZE_ADO_ID = -5` estaba declarado y jamás usado; v2 lo usa de verdad (patrón C2).
- **C12 (MENOR):** default de modelo corregido a `qwen3:32b` (tag real de Ollama para Qwen 3).
- **[ADICIÓN ARQUITECTO] A1 — health-check del servidor local:** nuevo `GET /api/llm/local-health` que hace un ping barato (timeout 3s) al endpoint configurado y la UI muestra el estado antes de invocar. Evita que el operador espere 120s para descubrir que Ollama no está corriendo. Cero trabajo extra: automático con la flag ON.

> Este documento está redactado para que un MODELO MENOR (Haiku, Codex CLI o GitHub
> Copilot Pro) lo implemente SIN inferir nada. Toda afirmación sobre código existente
> cita `archivo:línea` verificada el 2026-07-08 sobre el working tree
> (rama `codex/subida-cambios-pendientes`). Prohibido desviarse de los nombres exactos.

---

## 1. Objetivo + KPI

**Pedido textual del operador:** "Quiero integrar un modelo local Qwen 3 32B q4 en Stacky Agents.
Tengo Qwen 3 32B q4 corriendo localmente (probablemente vía Ollama o similar en un endpoint HTTP).
Quiero usarlo para casos de uso muy puntuales donde se le pase todo el contexto necesario de forma
determinista. NO quiero que el modelo use herramientas realmente (sin tool use). Casos de uso:
1. Análisis de código: pasar todo el contexto y que el modelo analice y responda
2. Creación de pipelines: que el modelo rellene automáticamente working directory, condition,
environment variables con todo el contexto necesario."

Se integra un **cliente LLM local** (`invoke_local_llm` en `copilot_bridge.py`) que habla con un
endpoint HTTP configurable (por defecto compatible Ollama:
`http://localhost:11434/v1/chat/completions`). Es **OpenAI-compatible** (Ollama, LM Studio, vLLM,
text-generation-webui). Los casos de uso se exponen como 2 endpoints backend especializados que
inyectan un prompt HITL sin tool use y van SIEMPRE al modelo local, independientemente del
`LLM_BACKEND` global (C1). Adicionalmente (F2, opcional/avanzado) se soporta
`LLM_BACKEND=local_llm` para quien quiera redirigir TODO el bridge al modelo local.

**KPIs (binarios):**
- **KPI-1 (config por UI):** el operador activa la flag y configura endpoint/modelo/timeout 100%
  desde la UI del Arnés (HarnessFlagsPanel). Cero edición manual de `.env` obligatoria (C7).
- **KPI-2 (análisis de código):** `POST /api/llm/analyze-code` con el contexto (archivos, proyecto,
  stack) devuelve un análisis en markdown del modelo LOCAL (no de Copilot), sin tool use.
- **KPI-3 (creación de pipelines):** `POST /api/llm/suggest-pipeline` con el spec parcial devuelve
  sugerencias de working directory, condition, environment variables del modelo LOCAL, sin tool
  use ni commits.
- **KPI-4 (runtime-agnóstico):** los endpoints son HTTP backend-side puros: cualquier consumidor
  (UI, los 3 runtimes vía MCP/HTTP, curl) los usa igual. NO se promete que Claude Code CLI /
  Codex CLI seleccionen el modelo local como su motor (imposible: spawnan binarios propios) (C5).
- **KPI-5 (HITL):** el modelo NUNCA aplica cambios; solo propone. La UI pre-rellena campos
  EDITABLES; el operador revisa y decide (F5).

---

## 2. Por qué ahora / gap que cierra

| Hecho verificado | Evidencia (archivo:línea) |
|---|---|
| `copilot_bridge.invoke()` despacha por `config.LLM_BACKEND` global | `backend/copilot_bridge.py:134-148` |
| `LogFn = Callable[[str, str], None]` — on_log recibe `(level, msg)` | `backend/copilot_bridge.py:120` |
| `BridgeResponse` tiene `text`, `format`, `metadata` | `backend/copilot_bridge.py:114-117` |
| `AgentExecution.ticket_id` es `nullable=False`; `input_context_json` y `started_by` NOT NULL | `backend/models.py:211,215,222` |
| `AgentExecution.metadata_dict` es property sobre `metadata_json` | `backend/models.py:260-264` |
| Patrón de ticket interno con `ado_id` negativo + `external_id=-ticket.id` único | `backend/api/devops_agent.py:63-75` |
| `FlagSpec.requires` es `str | None`; `group` es `"claude_code_cli" | "global"`; existe `type="str"` | `backend/services/harness_flags.py:21-41,2203` |
| Blueprints se registran en `api/__init__.py` vía `api_bp.register_blueprint(...)` | `backend/api/__init__.py:54-73` |
| Health vive en `api/diag.py` (NO existe `api/health.py`) | `backend/api/diag.py` (símbolo `health`) |
| NO existe soporte para modelos locales/Ollama en el código actual | grep sin resultados de `ollama`/`local_llm` en backend |

**Gap:** NO existe manera de usar un modelo local (Qwen, Llama, etc.) en Stacky Agents. El operador
tiene Qwen 3 32B q4 corriendo localmente y quiere aprovecharlo para análisis de código y pipelines
SIN tool use (solo lectura/propuesta). Cerrar el gap es barato: una función cliente
OpenAI-compatible en `copilot_bridge.py` + 2 endpoints especializados con prompt HITL + un
consumidor UI mínimo.

---

## 3. Principios y guardarraíles (NO negociables)

1. **Runtime-agnóstico (C5):** la capacidad vive en endpoints HTTP backend-side; ningún runtime
   la necesita ni la rompe. No se toca `agent_runner.py`.
2. **Cero trabajo extra para el operador (C7):** flag + 3 configs editables desde la UI del Arnés.
   Default OFF → byte-idéntico a hoy.
3. **Human-in-the-loop innegociable:** los endpoints inyectan un prompt que prohíbe tool use.
   El modelo responde texto/JSON; la UI pre-rellena campos EDITABLES; el operador decide.
4. **Mono-operador, sin auth real:** ningún concepto de roles/permisos. El endpoint local es
   `localhost` por default (configurable).
5. **OpenAI-compatible:** payload `model` + `messages` + `stream:false`; respuesta
   `choices[0].message.content`. Agnóstico al server (Ollama/LM Studio/vLLM).
6. **No degradar lo existente (C1):** los endpoints NUEVOS van directo al cliente local; el
   dispatch global de `invoke()`/`llm_router` solo cambia si el operador setea explícitamente
   `LLM_BACKEND=local_llm` (F2, avanzado, con advertencia). Todo es ADITIVO.
7. **Reusar, no reinventar:** mismo patrón HTTP `requests` de `copilot_bridge.py` (headers,
   timeout, manejo de status).
8. **Ratchet de tests (plan 49):** todo test backend nuevo se registra en
   `backend/scripts/run_harness_tests.sh` **y** `run_harness_tests.ps1`.
9. **Ayuda llana (plan 86):** cada flag nueva necesita entrada en `harness_flags_help.py`.
10. **Nunca 500 / nunca bloquear:** endpoint local caído → error descriptivo con hint accionable
    y timeout configurable; nunca 500 ni bloqueo infinito.
11. **Requires R4 (profundidad 1):** las flags hijas (`LOCAL_LLM_ENDPOINT`, `LOCAL_LLM_MODEL`,
    `LOCAL_LLM_TIMEOUT_SEC`) tienen `requires="LOCAL_LLM_ENABLED"`; la master NO tiene requires.
    Cada arista nueva se agrega a `_REQUIRES_MAP_FROZEN` en
    `backend/tests/test_harness_flags_requires.py`.

---

## 4. Diseño de una pasada (para entender antes de las fases)

```
Operador (UI Arnés: LOCAL_LLM_ENABLED=ON, endpoint/modelo/timeout editables)
   │
   ▼
GET /api/llm/local-health  ──ping 3s──▶ servidor local  →  badge "alcanzable / caído" en UI  [A1]
   │
   ▼
POST /api/llm/analyze-code {project, stack?, files[], prompt?}
POST /api/llm/suggest-pipeline {project, stack, spec_partial?}
   │
   ▼
api/local_llm_analysis.py: guard flag (404 si OFF) → ticket interno ado_id=-5 → AgentExecution
   │
   ▼
copilot_bridge.invoke_local_llm(system=HITL, user=contexto)  ← SIEMPRE al endpoint local (C1)
   │
   ▼
HTTP POST LOCAL_LLM_ENDPOINT (OpenAI-compatible, stream=false, timeout=LOCAL_LLM_TIMEOUT_SEC)
   │
   ▼
Respuesta (markdown / JSON) → execution completed → UI muestra propuesta EDITABLE (HITL)
```

**Modo avanzado (F2, opt-in explícito):** `LLM_BACKEND=local_llm` redirige TODO el tráfico de
`copilot_bridge.invoke()` y `llm_router` al modelo local. Documentado con advertencia: afecta a
todos los agentes que usan el bridge. Los endpoints de este plan NO dependen de este modo.

---

## 5. Fases

### F0 — Flags + configuración del modelo local (fundación)

**Objetivo:** 4 configs (`LOCAL_LLM_ENABLED` bool, `LOCAL_LLM_ENDPOINT` str, `LOCAL_LLM_MODEL` str,
`LOCAL_LLM_TIMEOUT_SEC` int) en `config.py` + registry del Arnés, editables por UI (C7), flag
master default OFF, health expuesto en `api/diag.py` (C9).

**Archivos a editar (todos aditivos):**

1. `Stacky Agents/backend/config.py` — junto al bloque de LLM existente (`LLM_BACKEND`/`LLM_MODEL`):
   ```python
   # Plan 106 — Modelo local (Qwen 3 32B q4 u otro, vía Ollama/LM Studio/vLLM).
   LOCAL_LLM_ENABLED: bool = os.getenv("LOCAL_LLM_ENABLED", "false").lower() in (
       "true", "1", "yes"
   )
   LOCAL_LLM_ENDPOINT: str = os.getenv(
       "LOCAL_LLM_ENDPOINT", "http://localhost:11434/v1/chat/completions"
   )
   LOCAL_LLM_MODEL: str = os.getenv("LOCAL_LLM_MODEL", "qwen3:32b")
   LOCAL_LLM_TIMEOUT_SEC: int = int(os.getenv("LOCAL_LLM_TIMEOUT_SEC", "120"))
   ```

2. `Stacky Agents/backend/services/harness_flags.py` — 4 `FlagSpec` nuevos con los CAMPOS REALES
   del dataclass (`harness_flags.py:21-41`), en la categoría donde viven las flags `LLM_*`/globales
   (buscar con grep la categoría que contiene `LLM_BACKEND` o, si no está, usar la misma categoría
   que `DEVOPS_*`; anotar la decisión en el commit):
   ```python
   FlagSpec(
       key="LOCAL_LLM_ENABLED",
       type="bool",
       label="Modelo local (Ollama/LM Studio/vLLM)",
       description="Habilita el cliente LLM local para análisis de código y sugerencias de pipeline con modelos como Qwen 3 32B q4.",
       group="global",
   ),
   FlagSpec(
       key="LOCAL_LLM_ENDPOINT",
       type="str",
       label="Endpoint del modelo local",
       description="URL OpenAI-compatible del servidor local (Ollama: http://localhost:11434/v1/chat/completions).",
       group="global",
       requires="LOCAL_LLM_ENABLED",
       default="http://localhost:11434/v1/chat/completions",
   ),
   FlagSpec(
       key="LOCAL_LLM_MODEL",
       type="str",
       label="Modelo local (tag)",
       description="Tag del modelo en el servidor local (ej. qwen3:32b).",
       group="global",
       requires="LOCAL_LLM_ENABLED",
       default="qwen3:32b",
   ),
   FlagSpec(
       key="LOCAL_LLM_TIMEOUT_SEC",
       type="int",
       label="Timeout modelo local (segundos)",
       description="Tiempo máximo de espera por respuesta del modelo local. Modelos 32B en CPU/GPU consumer pueden tardar minutos.",
       group="global",
       requires="LOCAL_LLM_ENABLED",
       default=120,
       min_value=10,
       max_value=600,
   ),
   ```
   - **NO agregar `default=` a `LOCAL_LLM_ENABLED`** (gotcha plan 63: los bool nuevos no van en
     `_CURATED_DEFAULTS_ON` y `default=False` explícito rompe `test_default_known_only_for_curated`).
     Los `default=` de las flags str/int SÍ van (no son bool; el test curado solo aplica a bools).
     Si algún test del registry falla por esos defaults, quitarlos y dejar type-zero: el default
     EFECTIVO ya vive en `config.py`.

3. `Stacky Agents/backend/tests/test_harness_flags_requires.py` — agregar 3 aristas a
   `_REQUIRES_MAP_FROZEN` (guardarraíl 11):
   ```python
   "LOCAL_LLM_ENDPOINT": "LOCAL_LLM_ENABLED",
   "LOCAL_LLM_MODEL": "LOCAL_LLM_ENABLED",
   "LOCAL_LLM_TIMEOUT_SEC": "LOCAL_LLM_ENABLED",
   ```
   (respetar el formato exacto que ya usa ese archivo; verificarlo con grep antes de editar).

4. `Stacky Agents/backend/services/harness_flags_help.py` — 4 entradas `PlainHelp` (una por flag),
   estilo llano plan 86. Ejemplo para la master:
   ```python
   "LOCAL_LLM_ENABLED": "Modelo local (Ollama/LM Studio/vLLM): permite usar un LLM corriendo en tu máquina para análisis de código y sugerencias de pipelines. Configurá el endpoint y el modelo en las flags de al lado.",
   ```

5. `Stacky Agents/backend/api/diag.py` (C9 — NO existe `api/health.py`) — dentro de la función
   `health` existente, agregar al dict de respuesta:
   ```python
   "local_llm_enabled": bool(getattr(config, "LOCAL_LLM_ENABLED", False)),  # Plan 106
   ```
   (solo la flag; endpoint/modelo se leen desde el panel de flags, no hace falta duplicarlos).

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan106_local_llm_config.py`:
- `test_f0_flag_default_off` — `config.LOCAL_LLM_ENABLED is False` con entorno limpio.
- `test_f0_flags_registered_in_registry` — las 4 keys existen en el registry; `LOCAL_LLM_ENABLED`
  sin `requires`; las otras 3 con `requires == "LOCAL_LLM_ENABLED"` (C4: string, no lista).
- `test_f0_flags_have_plain_help` — las 4 keys existen en el dict de `harness_flags_help`.
- `test_f0_config_defaults` — `LOCAL_LLM_ENDPOINT ==
  "http://localhost:11434/v1/chat/completions"`, `LOCAL_LLM_MODEL == "qwen3:32b"`,
  `LOCAL_LLM_TIMEOUT_SEC == 120`.
- `test_f0_health_exposes_local_llm_enabled` — el endpoint health de diag incluye
  `local_llm_enabled`.

**Comando:** `cd "Stacky Agents/backend" && venv/Scripts/python.exe -m pytest tests/test_plan106_local_llm_config.py -q`
**También correr (no-regresión):** `venv/Scripts/python.exe -m pytest tests/test_harness_flags.py tests/test_harness_flags_requires.py -q`

**Criterio binario:** los 5 tests nuevos + no-regresión verde.
**Flag:** `LOCAL_LLM_ENABLED` default OFF.
**Runtimes:** N/A (config pura). **Trabajo del operador:** opt-in 100% por UI (KPI-1).

---

### F1 — Cliente HTTP al modelo local (OpenAI-compatible)

**Objetivo:** función pública `invoke_local_llm()` en `copilot_bridge.py` que va SIEMPRE al
endpoint local (C1), con la firma REAL de `LogFn` (C3) y timeout configurable (C8). Además,
dispatch aditivo en `invoke()` para el modo avanzado `LLM_BACKEND=local_llm`.

**Archivo a EDITAR:** `Stacky Agents/backend/copilot_bridge.py`

1. Actualizar el docstring del módulo para mencionar `local_llm` (agregar una línea; no reescribir
   el docstring entero).

2. Agregar la función PÚBLICA `invoke_local_llm()` (nueva, cerca de `invoke()`):
   ```python
   def invoke_local_llm(
       *,
       agent_type: str,
       system: str,
       user: str,
       on_log: LogFn,
       execution_id: int | None = None,
       model: str | None = None,
   ) -> BridgeResponse:
       """Invoca el modelo LOCAL vía HTTP OpenAI-compatible (Ollama/LM Studio/vLLM).

       A DIFERENCIA de invoke(), NO mira config.LLM_BACKEND: va siempre al endpoint
       local configurado (LOCAL_LLM_ENDPOINT). Usada por api/local_llm_analysis.py.
       Levanta RuntimeError con mensaje accionable si el endpoint no responde.
       on_log recibe (level, msg) — firma LogFn real (copilot_bridge.py:120).
       """
       endpoint = config.LOCAL_LLM_ENDPOINT
       if not endpoint:
           raise RuntimeError(
               "LOCAL_LLM_ENDPOINT no está configurado. Sételo en el panel del Arnés "
               "(ej. http://localhost:11434/v1/chat/completions para Ollama)."
           )
       resolved_model = model or config.LOCAL_LLM_MODEL
       timeout_sec = int(getattr(config, "LOCAL_LLM_TIMEOUT_SEC", 120))

       payload = {
           "model": resolved_model,
           "messages": [
               {"role": "system", "content": system},
               {"role": "user", "content": user},
           ],
           "stream": False,
       }
       on_log("info", f"Invocando modelo local {resolved_model} en {endpoint}")
       try:
           response = requests.post(
               endpoint,
               headers={"Content-Type": "application/json"},
               json=payload,
               timeout=timeout_sec,
           )
       except requests.Timeout:
           raise RuntimeError(
               f"Endpoint local no respondió en {timeout_sec}s ({endpoint}). "
               "Verificá que Ollama/LLM server esté corriendo, o subí "
               "LOCAL_LLM_TIMEOUT_SEC en el panel del Arnés."
           )
       except requests.ConnectionError as e:
           raise RuntimeError(
               f"No se pudo conectar al endpoint local ({endpoint}): {e}"
           )
       if response.status_code != 200:
           body = response.text[:500]
           raise RuntimeError(
               f"Endpoint local devolvió HTTP {response.status_code}: {body}"
           )
       raw = response.json()
       choices = raw.get("choices") or []
       if not choices:
           raise RuntimeError(
               f"Respuesta del modelo local sin 'choices': {str(raw)[:500]}"
           )
       content = (choices[0].get("message") or {}).get("content", "")
       if not content:
           raise RuntimeError("Respuesta del modelo local vacía")
       on_log("info", f"Modelo local respondió con {len(content)} chars")
       return BridgeResponse(
           text=content,
           format="markdown",
           metadata={"model": resolved_model, "backend": "local_llm"},
       )
   ```
3. Modo avanzado (opt-in explícito): en `invoke()` (`copilot_bridge.py:134-148`), después del
   branch `mock`, agregar:
   ```python
   if backend == "local_llm":  # Plan 106 F1 — modo avanzado: TODO el bridge va al modelo local
       return invoke_local_llm(
           agent_type=agent_type, system=system, user=user,
           on_log=on_log, execution_id=execution_id, model=model,
       )
   ```

4. `list_copilot_models()` (`copilot_bridge.py:63`): agregar al INICIO de la función:
   ```python
   if config.LLM_BACKEND.lower() == "local_llm":  # Plan 106
       return [{
           "id": config.LOCAL_LLM_MODEL,
           "name": f"Modelo local ({config.LOCAL_LLM_MODEL})",
           "vendor": "local",
           "family": "",
           "preview": False,
           "capabilities": {"max_output_tokens": 8192},
       }]
   ```

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan106_local_llm_bridge.py`
(mockeando `requests.post` en el módulo `copilot_bridge` — gotcha plan 28: parchear en el módulo
que lo importa, `mock.patch("copilot_bridge.requests.post", ...)`):
- `test_f1_invoke_local_llm_success` — mock 200 con respuesta OpenAI → `BridgeResponse.text`
  correcto y `metadata["backend"] == "local_llm"`.
- `test_f1_invoke_local_llm_ignores_global_backend` — con `LLM_BACKEND="copilot"`,
  `invoke_local_llm()` IGUAL pega al endpoint local (C1: el mock de requests.post recibe la URL
  de `LOCAL_LLM_ENDPOINT`).
- `test_f1_invoke_local_llm_timeout` — mock lanza `requests.Timeout` → `RuntimeError` que menciona
  `LOCAL_LLM_TIMEOUT_SEC`.
- `test_f1_invoke_local_llm_connection_error` — mock lanza `requests.ConnectionError` →
  `RuntimeError` con hint.
- `test_f1_invoke_local_llm_non_200` — mock 500 → `RuntimeError` con el código HTTP.
- `test_f1_invoke_local_llm_missing_choices` — mock 200 sin `choices` → `RuntimeError`.
- `test_f1_invoke_local_llm_empty_content` — mock 200 con `content=""` → `RuntimeError`.
- `test_f1_invoke_local_llm_endpoint_required` — con `LOCAL_LLM_ENDPOINT=""` → `RuntimeError`.
- `test_f1_invoke_local_llm_uses_configured_timeout` — con `LOCAL_LLM_TIMEOUT_SEC=300`, el mock
  recibe `timeout=300` (C8).
- `test_f1_invoke_dispatch_local_llm_backend` — con `LLM_BACKEND="local_llm"`, `invoke()` llega a
  `invoke_local_llm` (mockear `requests.post`).
- `test_f1_list_models_local_backend` — con `LLM_BACKEND="local_llm"`, `list_copilot_models()`
  devuelve 1 dict con el modelo configurado.
- `test_f1_on_log_receives_level_and_msg` — el `on_log` pasado recibe exactamente 2 argumentos
  posicionales `(level, msg)` (C3: candado sobre la firma).

**Comando:** `cd "Stacky Agents/backend" && venv/Scripts/python.exe -m pytest tests/test_plan106_local_llm_bridge.py -q`

**Criterio binario:** los 12 tests en verde.
**Flag:** el cliente per-se no gatea por flag (gatea el endpoint F3/F4); el modo avanzado gatea
por `LLM_BACKEND=local_llm` explícito.
**Runtimes:** N/A (cliente backend). **Trabajo del operador:** ninguno adicional.

---

### F2 — Integración en llm_router (modo avanzado, opt-in)

**Objetivo:** si el operador setea explícitamente `LLM_BACKEND=local_llm`, `llm_router` lo
reconoce sin romperse. Los endpoints F3/F4 NO dependen de esta fase (C1).

**Archivo a EDITAR:** `Stacky Agents/backend/services/llm_router.py`

1. `_available_models()` (`llm_router.py:107`): agregar, después del branch `copilot`:
   ```python
   if backend == "local_llm":  # Plan 106 F2
       return [config.LOCAL_LLM_MODEL]
   ```

2. `decide()` (`llm_router.py:183`): agregar, ANTES del branch de copilot (después del early
   return de mock en `llm_router.py:219`):
   ```python
   if backend == "local_llm":  # Plan 106 F2
       return RoutingDecision(
           model=config.LOCAL_LLM_MODEL,
           reason="backend local_llm (modelo local configurado)",
       )
   ```
   (verificar con lectura los kwargs reales de `RoutingDecision` en el mismo archivo y usar
   exactamente esos; si tiene campos obligatorios extra, completarlos como hace el branch mock
   de `llm_router.py:219`).

3. NO tocar `_pick_copilot_default()`: con el early-return del punto 2, ese camino nunca se
   alcanza con backend `local_llm`.

**Tests PRIMERO** — EXTENDER `tests/test_plan106_local_llm_config.py`:
- `test_f2_available_models_local_backend` — con `LLM_BACKEND="local_llm"`,
  `_available_models() == [config.LOCAL_LLM_MODEL]`.
- `test_f2_decide_local_backend` — con `backend="local_llm"`, `decide()` devuelve
  `model == config.LOCAL_LLM_MODEL`.
- `test_f2_available_models_other_backend_unchanged` — con `LLM_BACKEND="anthropic"`,
  `_available_models()` NO incluye `config.LOCAL_LLM_MODEL` (salvo colisión de nombre, usar un
  `LOCAL_LLM_MODEL` de test único tipo `"qwen-test:1b"`).

**Comando:** `cd "Stacky Agents/backend" && venv/Scripts/python.exe -m pytest tests/test_plan106_local_llm_config.py -q`

**Criterio binario:** los 3 tests nuevos + los 5 de F0 (8 total) en verde.
**Runtimes:** N/A. **Trabajo del operador:** solo si opta por el modo avanzado (documentado con
advertencia en la PlainHelp de `LOCAL_LLM_ENABLED`: "el modo LLM_BACKEND=local_llm redirige TODOS
los agentes del bridge al modelo local").

---

### F3 — Blueprint + /api/llm/analyze-code + /api/llm/local-health [A1]

**Objetivo:** endpoint de análisis de código HITL contra el modelo local + health-check barato
del servidor local (ADICIÓN ARQUITECTO A1).

**Archivo NUEVO:** `Stacky Agents/backend/api/local_llm_analysis.py`

```python
"""api/local_llm_analysis.py — Plan 106 F3/F4. Endpoints del modelo local (HITL, sin tools).

GET  /api/llm/local-health     → ping barato al servidor local (A1).
POST /api/llm/analyze-code     → análisis de código (markdown).
POST /api/llm/suggest-pipeline → sugerencias de pipeline (F4).
"""
from __future__ import annotations

import json
from datetime import datetime

import requests
from flask import Blueprint, jsonify, request

import config
from db import session_scope
from models import AgentExecution, Ticket

bp = Blueprint("local_llm_analysis", __name__, url_prefix="/llm")

# Discriminador de identidad del ticket interno (sin ADO real), patrón
# api/devops_agent.py:63-75: ado_id negativo compartido + external_id=-ticket.id único.
_LOCAL_LLM_ADO_ID = -5

_HITL_RULES = (
    "\n\nREGLA ABSOLUTA (HITL):\n"
    "- NUNCA ejecutes comandos.\n"
    "- NUNCA edites archivos.\n"
    "- NUNCA commitees cambios.\n"
    "- NUNCA sugieras comandos que muten el estado del repo.\n"
    "- Solo analizá, explicá y proponé; el operador humano decide qué aplicar.\n"
)


def _flag_off() -> bool:
    return not getattr(config, "LOCAL_LLM_ENABLED", False)


def _guard():
    """404 si flag OFF; 503 si endpoint vacío; 400 si POST sin JSON."""
    if _flag_off():
        return jsonify({"error": "local_llm_disabled"}), 404
    if not getattr(config, "LOCAL_LLM_ENDPOINT", ""):
        return jsonify({"error": "local_llm_endpoint_not_configured"}), 503
    if request.method == "POST" and not request.is_json:
        return jsonify({"error": "body_required_json"}), 400
    return None


def _ensure_internal_ticket(session, project: str) -> Ticket:
    """Busca/crea el ticket interno del modelo local para este proyecto.

    Copia el patrón de api/devops_agent.py:63-75: ado_id=-5 discriminador (sin unique),
    external_id negativo único (=-ticket.id, seteado post-flush) para no chocar con el
    UNIQUE ux_tickets_stacky_tracker_external ni con el backfill de db.py.
    LEER devops_agent.py antes de implementar y replicar EXACTAMENTE los campos
    obligatorios de Ticket que ese código setea (title, work_item_type, project, etc.).
    """
    existing = (
        session.query(Ticket)
        .filter(Ticket.ado_id == _LOCAL_LLM_ADO_ID, Ticket.project == project)
        .first()
    )
    if existing:
        return existing
    ticket = Ticket(
        ado_id=_LOCAL_LLM_ADO_ID,
        project=project,
        stacky_project_name=project,
        title=f"[interno] Modelo local — {project}",
        work_item_type="Task",
        # completar el resto de campos NOT NULL igual que devops_agent.py:70-75
    )
    session.add(ticket)
    session.flush()
    ticket.external_id = -ticket.id
    return ticket


def _create_execution(session, ticket_id: int, agent_type: str, payload: dict) -> int:
    exec_row = AgentExecution(
        ticket_id=ticket_id,                       # NOT NULL (models.py:211)
        agent_type=agent_type,
        status="running",
        input_context_json=json.dumps(payload, ensure_ascii=False),  # NOT NULL (models.py:215)
        started_by="local_llm_api",                # NOT NULL (models.py:222)
        started_at=datetime.utcnow(),
    )
    exec_row.metadata_dict = {
        "backend": "local_llm",
        "model": getattr(config, "LOCAL_LLM_MODEL", ""),
    }
    session.add(exec_row)
    session.flush()
    return exec_row.id


def _finish_execution(execution_id: int, *, status: str, output: str = "", error: str = "") -> None:
    with session_scope() as session:
        exec_row = session.query(AgentExecution).filter_by(id=execution_id).first()
        if not exec_row:
            return
        exec_row.status = status
        exec_row.completed_at = datetime.utcnow()
        if output:
            exec_row.output = output[:10000]
        if error:
            exec_row.error_message = error[:500]


@bp.get("/local-health")
def local_health_route():
    """Ping barato (3s) al servidor local para que la UI muestre el estado. [A1]"""
    guard = _guard()
    if guard:
        return guard
    endpoint = config.LOCAL_LLM_ENDPOINT
    # Derivar la base del server: para .../v1/chat/completions probamos .../v1/models.
    base = endpoint.split("/v1/")[0] if "/v1/" in endpoint else endpoint
    try:
        resp = requests.get(f"{base}/v1/models", timeout=3)
        reachable = resp.status_code == 200
    except requests.RequestException:
        reachable = False
    return jsonify({
        "ok": True,
        "reachable": reachable,
        "endpoint": endpoint,
        "model": config.LOCAL_LLM_MODEL,
    })


@bp.post("/analyze-code")
def analyze_code_route():
    """Analiza código con el modelo local (sin tool use).

    Body: {"project": str (required), "stack": str (optional, default "generic"),
           "files": [{"path": str, "content": str}] (optional), "prompt": str (optional)}
    200: {"ok": true, "analysis": str, "model": str, "execution_id": int}
    """
    guard = _guard()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    project = body.get("project")
    if not project:
        return jsonify({"error": "project_required"}), 400
    stack = body.get("stack", "generic")
    files = body.get("files") or []
    custom_prompt = body.get("prompt") or ""

    system = (
        "Sos un ingeniero senior experto en análisis de código estático. "
        "Tu ÚNICA tarea es analizar y explicar en markdown." + _HITL_RULES
    )
    files_context = ""
    for f in files:
        files_context += f"\n--- {f.get('path', '')} ---\n{f.get('content', '')}\n"
    if files_context:
        files_context = "\n\n== ARCHIVOS ==\n" + files_context
    question = custom_prompt or "¿Qué observaciones tenés sobre este código?"
    user_prompt = (
        f'Analizá el código del proyecto "{project}" (stack: {stack}).'
        f"{files_context}\nPregunta del operador: {question}\n\n"
        "Respondé en markdown con secciones:\n"
        "1. Hallazgos (bugs, smells, riesgos)\n"
        "2. Sugerencias (refactors, patrones, mejores prácticas)\n"
        "3. Preguntas (para el operador)\n"
    )

    from copilot_bridge import invoke_local_llm  # import lazy (patrón del repo)

    with session_scope() as session:
        ticket = _ensure_internal_ticket(session, project)
        execution_id = _create_execution(
            session, ticket.id, "local_llm_analyzer",
            {"project": project, "stack": stack, "files": len(files)},
        )
    try:
        response = invoke_local_llm(
            agent_type="local_llm_analyzer",
            system=system,
            user=user_prompt,
            on_log=lambda level, msg: None,  # firma LogFn real (level, msg) — C3
            execution_id=execution_id,
        )
    except Exception as e:
        _finish_execution(execution_id, status="error", error=str(e))
        return jsonify({"ok": False, "error": str(e), "execution_id": execution_id}), 502
    _finish_execution(execution_id, status="completed", output=response.text)
    return jsonify({
        "ok": True,
        "analysis": response.text,
        "model": config.LOCAL_LLM_MODEL,
        "execution_id": execution_id,
    })
```

**Registro del blueprint:** en `Stacky Agents/backend/api/__init__.py`, junto a los imports y
registros existentes (`api/__init__.py:54-73`):
```python
from .local_llm_analysis import bp as local_llm_analysis_bp  # Plan 106
api_bp.register_blueprint(local_llm_analysis_bp)
```
(OJO gotcha plan 74: el blueprint ya tiene `url_prefix="/llm"`; NO agregar otro prefijo al
registrarlo — queda `/api/llm/...`.)

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan106_analyze_code_api.py`
(mockear `copilot_bridge.invoke_local_llm` — se importa lazy dentro de la ruta, así que
parchear en el módulo origen: `mock.patch("copilot_bridge.invoke_local_llm", ...)`, gotcha plan 28):
- `test_f3_flag_off_404` — `LOCAL_LLM_ENABLED=False` → 404 en analyze-code Y en local-health.
- `test_f3_endpoint_empty_503` — flag ON + `LOCAL_LLM_ENDPOINT=""` → 503.
- `test_f3_no_project_400` — body sin `project` → 400.
- `test_f3_no_json_400` — POST form-encoded → 400.
- `test_f3_success_returns_markdown_analysis` — mock → 200 con `analysis` y `execution_id`.
- `test_f3_invoke_receives_hitl_prompt` — el `system` que recibe el mock contiene
  "REGLA ABSOLUTA (HITL)" y "NUNCA ejecutes comandos".
- `test_f3_execution_created_and_completed` — se creó `AgentExecution` con
  `started_by="local_llm_api"`, `ticket` interno con `ado_id==-5`, y quedó `status="completed"`.
- `test_f3_error_marks_execution_error_502` — mock levanta `RuntimeError` → 502 y
  `status="error"` con `error_message` seteado.
- `test_f3_local_health_reachable_and_unreachable` — mock de `requests.get` en el módulo
  `api.local_llm_analysis`: 200 → `reachable=True`; `ConnectionError` → `reachable=False` (A1).

**Comando:** `cd "Stacky Agents/backend" && venv/Scripts/python.exe -m pytest tests/test_plan106_analyze_code_api.py -q`

**Criterio binario:** los 9 tests en verde.
**Flag:** `LOCAL_LLM_ENABLED` (gate duro 404).
**Runtimes:** endpoint HTTP puro (KPI-4). **Trabajo del operador:** opt-in (flag ON por UI).

---

### F4 — /api/llm/suggest-pipeline (sugerencias de pipeline)

**Objetivo:** endpoint que recibe un spec parcial de pipeline y devuelve sugerencias de
working directory, condition, environment variables SIN tool use.

**Archivo a EDITAR:** `Stacky Agents/backend/api/local_llm_analysis.py` (agregar ruta; `json` ya
está importado a nivel módulo — C6):

```python
@bp.post("/suggest-pipeline")
def suggest_pipeline_route():
    """Sugiere campos de pipeline con el modelo local (sin tool use).

    Body: {"project": str (required), "stack": str (required),
           "spec_partial": dict (optional)}
    200: {"ok": true, "suggestions": {working_directory, condition,
          environment_variables, justification}, "model": str, "execution_id": int}
    """
    guard = _guard()
    if guard:
        return guard
    body = request.get_json(silent=True) or {}
    project = body.get("project")
    stack = body.get("stack")
    if not project or not stack:
        return jsonify({"error": "project_and_stack_required"}), 400
    spec_partial = body.get("spec_partial") or {}

    system = (
        "Sos un ingeniero DevOps senior experto en pipelines CI/CD. "
        "Tu ÚNICA tarea es sugerir campos de pipeline en formato JSON." + _HITL_RULES
    )
    spec_context = json.dumps(spec_partial, ensure_ascii=False, indent=2)
    user_prompt = (
        f'Dado el proyecto "{project}" (stack: {stack}) y el spec parcial:\n'
        f"== SPEC PARCIAL ==\n{spec_context}\n\n"
        "Sugerí valores para estos campos del pipeline:\n"
        "1. working_directory: directorio de trabajo relativo a la raíz del repo\n"
        "2. condition: condición (branch/tag) que dispara el pipeline\n"
        "3. environment_variables: variables de entorno sugeridas (dict JSON)\n\n"
        "Respondé EXCLUSIVAMENTE con un objeto JSON (sin markdown) con las keys:\n"
        '{"working_directory": "...", "condition": "...", '
        '"environment_variables": {"VAR": "valor"}, '
        '"justification": "explicación breve en castellano"}\n'
        "Si no estás seguro de un campo, dejalo vacío (string vacío o dict vacío).\n"
    )

    from copilot_bridge import invoke_local_llm

    with session_scope() as session:
        ticket = _ensure_internal_ticket(session, project)
        execution_id = _create_execution(
            session, ticket.id, "local_llm_pipeline_suggester",
            {"project": project, "stack": stack, "spec_partial": spec_partial},
        )
    try:
        response = invoke_local_llm(
            agent_type="local_llm_pipeline_suggester",
            system=system,
            user=user_prompt,
            on_log=lambda level, msg: None,
            execution_id=execution_id,
        )
    except Exception as e:
        _finish_execution(execution_id, status="error", error=str(e))
        return jsonify({"ok": False, "error": str(e), "execution_id": execution_id}), 502

    text = response.text.strip()
    if text.startswith("```"):
        # Quitar fence markdown (```json ... ```)
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) >= 3 else text
    try:
        suggestions = json.loads(text)
    except json.JSONDecodeError as e:
        _finish_execution(execution_id, status="error", error=f"JSON parse error: {e}")
        return jsonify({
            "ok": False,
            "error": "json_parse_error",
            "message": "El modelo no devolvió JSON válido; reintentá.",
            "raw_response": response.text[:500],
            "execution_id": execution_id,
        }), 502
    _finish_execution(execution_id, status="completed", output=text)
    return jsonify({
        "ok": True,
        "suggestions": suggestions,
        "model": config.LOCAL_LLM_MODEL,
        "execution_id": execution_id,
    })
```

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan106_suggest_pipeline_api.py`
(mismo patrón de mock que F3):
- `test_f4_flag_off_404` — flag OFF → 404.
- `test_f4_no_project_or_stack_400` — body sin `project` o sin `stack` → 400.
- `test_f4_success_returns_suggestions_json` — mock devuelve JSON plano → 200 con
  `suggestions.working_directory/condition/environment_variables/justification`.
- `test_f4_parse_strips_markdown_fence` — mock devuelve `"```json\n{...}\n```"` → parsea OK.
- `test_f4_json_parse_error_502` — mock devuelve texto no-JSON → 502 con
  `error="json_parse_error"` y `raw_response`, y la execution queda `status="error"`.
- `test_f4_invoke_receives_hitl_prompt` — el `system` del mock contiene "REGLA ABSOLUTA (HITL)".

**Comando:** `cd "Stacky Agents/backend" && venv/Scripts/python.exe -m pytest tests/test_plan106_suggest_pipeline_api.py -q`

**Criterio binario:** los 6 tests en verde.
**Flag:** heredada de F0. **Runtimes:** endpoint HTTP puro. **Trabajo del operador:** opt-in.

---

### F5 — Frontend: clientes API + consumidor UI mínimo (HITL)

**Objetivo (C10):** el operador usa la feature desde la UI, no desde curl: botón
"Sugerir con IA local" en el builder de pipelines que PRE-RELLENA campos editables, y badge de
alcanzabilidad del servidor local [A1].

**Archivos:**

1. `Stacky Agents/frontend/src/api/endpoints.ts` — agregar (respetar el patrón de los `*Api`
   existentes en el archivo; verificar con grep cómo exportan y tipan los vecinos):
   ```ts
   /** Plan 106 — Modelo local (Ollama/LM Studio/vLLM). */
   export const LocalLlmApi = {
     localHealth: () =>
       api.get<{ ok: boolean; reachable: boolean; endpoint: string; model: string }>(
         "/api/llm/local-health",
       ),
     analyzeCode: (body: {
       project: string;
       stack?: string;
       files?: Array<{ path: string; content: string }>;
       prompt?: string;
     }) =>
       api.post<{ ok: boolean; analysis: string; model: string; execution_id: number }>(
         "/api/llm/analyze-code",
         body,
       ),
     suggestPipeline: (body: {
       project: string;
       stack: string;
       spec_partial?: Record<string, unknown>;
     }) =>
       api.post<{
         ok: boolean;
         suggestions: {
           working_directory: string;
           condition: string;
           environment_variables: Record<string, string>;
           justification: string;
         };
         model: string;
         execution_id: number;
       }>("/api/llm/suggest-pipeline", body),
   };
   ```

2. `Stacky Agents/frontend/src/components/devops/PipelineBuilderSection.tsx` — consumidor mínimo
   (C10). Ubicar con grep la zona donde se editan los campos del pipeline (working directory /
   variables; el plan 97 integró su detector cerca de `starterSpec`). Agregar:
   - un botón `Sugerir con IA local` visible SOLO si el health del arnés reporta
     `local_llm_enabled=true` (leerlo de la misma fuente que la sección ya usa para gatear
     features por flag; si la sección no tiene esa fuente, obtenerlo con `LocalLlmApi.localHealth()`
     y ocultar el botón si responde 404);
   - al click: llama `LocalLlmApi.suggestPipeline({project, stack, spec_partial})` con el estado
     actual del builder, muestra spinner, y al éxito PRE-RELLENA los inputs de working directory /
     condition / variables SOLO si están vacíos (nunca pisa lo que el operador ya escribió) y
     muestra `justification` como texto ayuda. El operador puede editar todo antes de guardar
     (KPI-5, HITL);
   - junto al botón, un badge con el resultado de `localHealth()` ("IA local: disponible" /
     "IA local: sin conexión") [A1].
   - Si la llamada falla (502/timeout), mostrar el mensaje de error del backend en el mismo patrón
     de error que la sección ya usa; NUNCA romper el builder.

3. La flag `LOCAL_LLM_ENABLED` y las 3 configs aparecen automáticamente en
   `frontend/src/components/HarnessFlagsPanel.tsx` vía el registry genérico (plan 33); no editar
   ese archivo salvo que `tsc` falle.

**Tests:**
- `npx tsc --noEmit` → 0 errores.
- `grep -n "LocalLlmApi" "Stacky Agents/frontend/src/api/endpoints.ts"` → ≥1 ocurrencia.
- `grep -n "LocalLlmApi" "Stacky Agents/frontend/src/components/devops/PipelineBuilderSection.tsx"` → ≥1 ocurrencia.
- (Opcional si el harness de vitest de la sección ya existe: test de que el botón no renderiza
  con flag OFF. Correr vitest POR ARCHIVO.)

**Criterio binario:** `tsc` 0 err + los 2 greps pasan.
**Flag:** botón y badge gateados por `LOCAL_LLM_ENABLED`. **Runtimes:** UI runtime-agnóstica.
**Trabajo del operador:** cero (aparece solo con la flag ON).

---

### F6 — Cierre: ratchet, export de defaults, doc

**Objetivo:** blindaje e higiene de serie.

1. **Ratchet de tests (plan 49):** agregar los 4 archivos de test backend nuevos a
   `HARNESS_TEST_FILES` en `backend/scripts/run_harness_tests.sh` **y** `run_harness_tests.ps1`:
   - `test_plan106_local_llm_config.py`
   - `test_plan106_local_llm_bridge.py`
   - `test_plan106_analyze_code_api.py`
   - `test_plan106_suggest_pipeline_api.py`

2. **harness_defaults.env:** NO editar a mano. Dejar constancia en la sección de estado
   de ESTE doc de que las flags nuevas nacen con sus defaults de `config.py` y que el export
   (`deployment/export_harness_defaults.py`) las incorporará en la próxima corrida del operador.

3. **Actualizar encabezado de estado de ESTE doc** al implementar (riel del pipeline).

4. **No-regresión dirigida (por archivo, venv):**
   ```bash
   venv/Scripts/python.exe -m pytest tests/test_llm_router.py tests/test_harness_flags.py tests/test_harness_flags_requires.py -q
   ```

**Criterio binario:** ratchet verde + no-regresión verde.
**Trabajo del operador:** ninguno.

---

## 6. Cómo se honran los 5 KPIs (mapa KPI → mecanismo → test)

| KPI | Mecanismo | Verificación |
|---|---|---|
| **KPI-1 (config por UI)** | 4 FlagSpec en el registry (bool + 2 str + 1 int) editables en HarnessFlagsPanel | `test_f0_flags_registered_in_registry`, `test_f0_flags_have_plain_help` |
| **KPI-2 (análisis código)** | `POST /api/llm/analyze-code` → `invoke_local_llm()` SIEMPRE al endpoint local | `test_f3_success_returns_markdown_analysis`, `test_f1_invoke_local_llm_ignores_global_backend` |
| **KPI-3 (creación pipelines)** | `POST /api/llm/suggest-pipeline` → JSON de sugerencias del modelo local | `test_f4_success_returns_suggestions_json`, `test_f4_invoke_receives_hitl_prompt` |
| **KPI-4 (runtime-agnóstico)** | endpoints HTTP backend puros; ningún runtime tocado (no se edita `agent_runner.py`) | por construcción + no-regresión F6.4 |
| **KPI-5 (HITL)** | prompts con `_HITL_RULES` + UI pre-rellena campos EDITABLES sin pisar lo escrito | `test_f3_invoke_receives_hitl_prompt`, `test_f4_invoke_receives_hitl_prompt`, F5 |

---

## 7. Riesgos y mitigaciones

| Riesgo | Severidad | Mitigación |
|---|---|---|
| El endpoint local (Ollama) no responde | MEDIO | health-check A1 con badge en UI + timeout configurable (`LOCAL_LLM_TIMEOUT_SEC`) + `RuntimeError` con hint accionable |
| Timeout corto mata análisis grandes con 32B q4 | MEDIO | default 120s, configurable por UI hasta 600s (C8) |
| El modelo local ignora el prompt HITL | BAJO | no se le pasa tool config (imposible ejecutar); la UI solo PRE-RELLENA campos editables; el operador aplica |
| JSON inválido en `suggest-pipeline` | BAJO | fence-strip + `json.JSONDecodeError` → 502 con `raw_response` para debug; el operador reintenta |
| `LLM_BACKEND=local_llm` redirige TODO el bridge sin querer | MEDIO | modo avanzado separado del feature principal (C1); advertencia en PlainHelp; los endpoints nunca lo requieren |
| Tickets internos `ado_id=-5` chocan con backfill/unique | BAJO | patrón probado de `devops_agent.py:63-75` (`external_id=-ticket.id`) |
| El modelo local no es OpenAI-compatible | BAJO | Ollama, LM Studio, vLLM lo son; si no, el operador elige otro server |

---

## 8. Fuera de scope

- Streaming de respuestas (`stream=False`; streaming = mejora futura).
- Auth con Bearer token para el endpoint local (asumimos `localhost` sin auth; si hace falta,
  `LOCAL_LLM_API_KEY` futuro).
- Sección UI dedicada para `analyze-code` (v2 entrega el cliente API; el consumidor UI mínimo
  es el de pipelines, que es el caso de uso con campos estructurados).
- Usar el modelo local como MOTOR de los 3 runtimes CLI (imposible por diseño de los CLIs — C5).
- Integración con la "memoria que empuja" (planes 48-54) — diferible.

---

## 9. Glosario

- **cliente LLM local (`invoke_local_llm`):** función de `copilot_bridge.py` que va SIEMPRE al
  endpoint local configurado, sin mirar `LLM_BACKEND` global.
- **modo avanzado `LLM_BACKEND=local_llm`:** opt-in explícito que redirige TODO el tráfico del
  bridge (y `llm_router`) al modelo local. Separado del feature principal.
- **OpenAI-compatible:** endpoint que acepta payloads OpenAI (`/v1/chat/completions`, `model`,
  `messages`, `stream`) y responde `choices[0].message.content`.
- **Ollama / LM Studio / vLLM:** servers locales de LLMs OpenAI-compatible; Ollama default
  `http://localhost:11434`.
- **ticket interno `ado_id=-5`:** ticket discriminador sin ADO real que ancla las
  `AgentExecution` de este plan (patrón `devops_agent.py`).
- **HITL:** Human-in-the-loop. Los endpoints prohíben tools; la UI pre-rellena campos editables;
  el operador decide.

---

## 10. Orden de implementación

1. F0 (flags + configuración, UI-editable) — tests → código → verde.
2. F1 (cliente `invoke_local_llm` + dispatch avanzado) — tests → código → verde.
3. F2 (llm_router, modo avanzado) — tests → código → verde.
4. F3 (blueprint + analyze-code + local-health) — tests → código → verde.
5. F4 (suggest-pipeline) — tests → código → verde.
6. F5 (frontend: clientes + botón HITL + badge) — código → tsc 0 err + greps.
7. F6 (ratchet + no-regresión + estado del doc).

---

## 11. Definición de Hecho (DoD)

- [ ] 4 archivos de test backend nuevos verdes (≈32 tests: F0=5+F2=3, F1=12, F3=9, F4=6)
      corridos POR ARCHIVO con el venv.
- [ ] No-regresión dirigida verde (F6.4).
- [ ] Flag OFF ⇒ 404 en los 3 endpoints (`local-health`, `analyze-code`, `suggest-pipeline`).
- [ ] `test_f1_invoke_local_llm_ignores_global_backend` verde (candado C1: nunca desvía a Copilot).
- [ ] Las 4 flags visibles y editables en HarnessFlagsPanel (KPI-1) — verificación manual 1 min.
- [ ] Botón "Sugerir con IA local" pre-rellena sin pisar valores del operador (KPI-5) —
      verificación manual 1 min.
- [ ] Ratchet actualizado en sh y ps1.
- [ ] Commits por fase SOLO con archivos de este plan (jamás `git add -A`).
- [ ] Encabezado de estado de este doc actualizado a IMPLEMENTADO con hashes.
