# Plan 106 — Modelo local Qwen 3 para análisis de código y creación de pipelines

**Estado:** PROPUESTO v1
**Fecha:** 2026-07-08
**Dependencias:** planes 40-46 (runtimes), 71 (CI providers agnósticos), 87-91 (serie DevOps), 97 (presets por stack)
**No depende de:** planes 93-96, 98-105

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

Se integra un **backend LLM local** (`local_llm`) que habla con un endpoint HTTP configurable
(por defecto compatible Ollama: `http://localhost:11434/v1/chat/completions`) y expone el modelo
local Qwen 3 32B q4 como una opción más en el ecosistema Stacky. El backend es **OpenAI-compatible**
(para funcionar con Ollama, LM Studio, vLLM, etc.) y se integra en el `llm_router` y
`copilot_bridge` como una opción más. Los casos de uso específicos se exponen como prompts
especiales que NO invocan tools (solo análisis y propuesta).

**KPIs (binarios):**
- **KPI-1 (config):** el operador configura 3 variables de entorno (endpoint, modelo, flag ON) y el
  modelo local aparece en la lista de modelos disponibles. Cero pasos manuales adicionales.
- **KPI-2 (análisis de código):** el operador invoca un endpoint `/api/llm/analyze-code` con el
  contexto (archivos, proyecto, stack) y recibe un análisis en markdown sin que el modelo intente
  ejecutar tools.
- **KPI-3 (creación de pipelines):** el operador invoca un endpoint `/api/llm/suggest-pipeline` con
  el spec parcial del pipeline y recibe sugerencias de working directory, condition, environment
  variables, sin que el modelo intente ejecutar tools ni commitear.
- **KPI-4 (paridad 3 runtimes):** los 3 runtimes (Codex CLI, Claude Code CLI, GitHub Copilot Pro)
  pueden usar el modelo local vía `model_override` o selección en UI.
- **KPI-5 (HITL):** el modelo NUNCA aplica cambios automáticamente; solo propone. El operador
  decide qué aplicar.

---

## 2. Por qué ahora / gap que cierra

| Hecho verificado | Evidencia (archivo:línea) |
|---|---|
| `llm_router.py` ya soporta backends `anthropic`, `copilot`, `vscode_bridge`, `mock` | `backend/services/llm_router.py:8-10` |
| `copilot_bridge.py` ya implementa un cliente HTTP OpenAI-compatible para GitHub Models | `backend/copilot_bridge.py:63-110` |
| `agent_runner.py` despacha runtimes y acepta `model_override` | `backend/agent_runner.py:86-94,219-373` |
| `config.py` ya tiene `LLM_BACKEND`, `LLM_MODEL`, `COPILOT_ENDPOINT` | `backend/config.py:75-90` |
| NO existe soporte para modelos locales/Ollama en el código actual | grep sin resultados de `ollama`/`local` en backend |
| El plan 97 (presets por stack) ya tiene `pipeline_stack_detector.py` | `backend/services/pipeline_stack_detector.py` (verificado en plan 104) |
| El plan 87-91 estableció el panel DevOps y su contrato de extensión | docs/planes 87-91 IMPLEMENTADOS |

**Gap:** NO existe manera de usar un modelo local (Qwen, Llama, etc.) en Stacky Agents. El operador
tiene Qwen 3 32B q4 corriendo localmente y quiere aprovecharlo para análisis de código y pipelines
SIN tool use (solo lectura/propuesta). Cerrar el gap es barato: reusar el patrón OpenAI-compatible
de `copilot_bridge` + agregar un backend `local_llm` + 2 endpoints especializados (analyze-code,
suggest-pipeline) que inyectan un prompt HITL que prohíbe tools.

---

## 3. Principios y guardarraíles (NO negociables)

1. **3 runtimes con paridad (Codex CLI / Claude Code CLI / GitHub Copilot Pro):** el modelo local
   es un backend más (`local_llm`) que los 3 runtimes pueden usar vía `model_override` o selección
   en UI. Nada atado a un runtime específico.
2. **Cero trabajo extra para el operador:** 3 variables de entorno (endpoint, modelo, flag ON) →
   el modelo aparece disponible. Default OFF → byte-idéntico a hoy.
3. **Human-in-the-loop innegociable:** los endpoints especializados inyectan un prompt que
   prohíbe tool use ("NUNCA ejecutes comandos, NUNCA edites archivos, NUNCA commiteás; solo
   analizá y proponé en markdown"). El modelo responde texto; el operador decide.
4. **Mono-operador, sin auth real:** ningún concepto de roles/permisos. El endpoint local es
   `localhost` por default (configurable).
5. **OpenAI-compatible:** el backend habla con endpoints compatibles OpenAI (Ollama, LM Studio,
   vLLM, text-generation-webui). Esto lo hace agnóstico a la tecnología de serving.
6. **No degradar lo existente:** `llm_router`, `copilot_bridge`, `agent_runner`, `config.py` NO
   cambian su comportamiento con la flag OFF. Todo es ADITIVO.
7. **Reusar, no reinventar:** el reusar el patrón HTTP de `copilot_bridge.py` (cliente `requests`,
   headers OpenAI, body compatible) → NO duplicar código de cliente HTTP.
8. **Ratchet de tests (plan 49):** todo test backend nuevo se registra en
   `backend/scripts/run_harness_tests.sh` **y** `run_harness_tests.ps1`.
9. **Ayuda llana (plan 86):** la flag nueva necesita `PlainHelp`.
10. **Nunca 500 / nunca bloquear:** si el endpoint local no responde → error descriptivo
    ("endpoint local no responde en <URL>; verificá que Ollama/LLM server esté corriendo"),
    nunca 500 ni bloqueo infinito (timeout).

---

## 4. Diseño de una pasada (para entender antes de las fases)

```
Operador (configura .env: LOCAL_LLM_ENABLED=true, LOCAL_LLM_ENDPOINT=http://localhost:11434/v1/chat/completions, LOCAL_LLM_MODEL=qwen:32b)
   │
   ▼
Stacky boot (config.py lee las 3 vars, LOCAL_LLM_ENABLED default false)
   │
   ▼
llm_router.py: backend == "local_llm" → despacha a copilot_bridge con endpoint custom
   │
   ▼
copilot_bridge.py: invoke() con backend == "local_llm" → HTTP POST a LOCAL_LLM_ENDPOINT
   │
   ▼
Respuesta del modelo local (texto en markdown) → BridgeResponse → el operador la ve
```

**Endpoints especializados:**

```
POST /api/llm/analyze-code {project, stack?, files[], prompt?}
   → prompt HITL + contexto → modelo local → markdown de análisis

POST /api/llm/suggest-pipeline {spec_partial, stack, project}
   → prompt HITL + spec → modelo local → sugerencias (working_dir, condition, env_vars)
```

Ambos endpoints usan el backend `local_llm` (vía `llm_router.decide` o directamente) e inyectan
el prompt HITL que prohíbe tools.

---

## 5. Fases

### F0 — Flag + configuración del modelo local (fundación)

**Objetivo:** 3 variables de entorno (`LOCAL_LLM_ENABLED`, `LOCAL_LLM_ENDPOINT`,
`LOCAL_LLM_MODEL`) visibles en config, con flag default OFF y requires correcto.

**Archivos a editar (todos aditivos):**

1. `Stacky Agents/backend/config.py` — junto al bloque de LLM (`config.py:75-90`):
   ```python
   # Plan 106 — Modelo local (Qwen 3 32B q4 u otro, vía Ollama/LM Studio/vLLM).
   LOCAL_LLM_ENABLED: bool = os.getenv("LOCAL_LLM_ENABLED", "false").lower() in (
       "true", "1", "yes"
   )
   LOCAL_LLM_ENDPOINT: str = os.getenv(
       "LOCAL_LLM_ENDPOINT", "http://localhost:11434/v1/chat/completions"
   )
   LOCAL_LLM_MODEL: str = os.getenv("LOCAL_LLM_MODEL", "qwen:32b")
   ```

2. `Stacky Agents/backend/services/harness_flags.py`:
   - agregar `"LOCAL_LLM_ENABLED"` a la categoría `core` (vecinas en `harness_flags.py:150-160`);
   - agregar el `FlagSpec`:
     ```python
     FlagSpec(
         key="LOCAL_LLM_ENABLED",
         type="bool",
         label="Modelo local (Ollama/LM Studio/vLLM)",
         description="Habilita el backend LLM local para usar modelos como Qwen 3 32B q4. Requiere configurar LOCAL_LLM_ENDPOINT y LOCAL_LLM_MODEL.",
         group="experimental",
         requires=[],  # No depende de otra flag
     )
     ```
   - **NO agregar `default=`** (gotcha plan 63).

3. `Stacky Agents/backend/tests/test_harness_flags_requires.py` — si esta flag tuviera `requires`,
   agregar la arista a `_REQUIRES_MAP_FROZEN`. Como `requires=[]`, NO se toca este archivo.

4. `Stacky Agents/backend/services/harness_flags_help.py` — entrada `PlainHelp`:
   ```python
   "LOCAL_LLM_ENABLED": "Modelo local (Ollama/LM Studio/vLLM): permite usar un LLM corriendo en tu máquina para análisis de código y sugerencias de pipelines. Configurá LOCAL_LLM_ENDPOINT y LOCAL_LLM_MODEL antes de activar.",
   ```

5. `Stacky Agents/backend/api/health.py` (o el endpoint de health existente) — agregar al health
   block (buscar el bloque que expone flags de stacky):
   ```python
   "local_llm_enabled": bool(getattr(cfg, "LOCAL_LLM_ENABLED", False)),  # Plan 106
   "local_llm_endpoint": str(getattr(cfg, "LOCAL_LLM_ENDPOINT", "")),  # Plan 106
   "local_llm_model": str(getattr(cfg, "LOCAL_LLM_MODEL", "")),  # Plan 106
   ```

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan106_local_llm_config.py`:
- `test_f0_flag_default_off` — `config.config.LOCAL_LLM_ENABLED is False` con entorno limpio.
- `test_f0_flag_registered_in_registry` — la key existe en el registry con `env_only=False`
  y `requires==[]`.
- `test_f0_flag_has_plain_help` — la key existe en el dict de `harness_flags_help`.
- `test_f0_config_has_endpoint_and_model_defaults` — `LOCAL_LLM_ENDPOINT` es
  `"http://localhost:11434/v1/chat/completions"` por default; `LOCAL_LLM_MODEL` es `"qwen:32b"`.
- `test_f0_health_exposes_local_llm` — `GET /health` incluye `local_llm_enabled`, `endpoint`,
  `model`.

**Comando:** `cd "Stacky Agents/backend" && venv/Scripts/python.exe -m pytest tests/test_plan106_local_llm_config.py -q`
**También correr (no-regresión):** `venv/Scripts/python.exe -m pytest tests/test_harness_flags.py -q`

**Criterio binario:** los 5 tests nuevos + no-regresión verde.
**Flag:** `LOCAL_LLM_ENABLED` default OFF.
**Runtimes:** N/A (config pura). **Trabajo del operador:** opt-in (setear las 3 vars de entorno).

---

### F1 — Bridge HTTP al modelo local (OpenAI-compatible)

**Objetivo:** `copilot_bridge.py` soporta backend `local_llm` con endpoint configurable
y modelo custom, reusando el patrón OpenAI-compatible existente.

**Archivo a EDITAR:** `Stacky Agents/backend/copilot_bridge.py`

1. Actualizar el docstring para mencionar `local_llm`:
   ```python
   """
   Bridge al engine LLM real (copilot / local / mock).

   - mock: outputs canned para validar la UI sin gastar tokens.
   - copilot: GitHub Copilot Chat API real (OpenAI-compatible).
   - local_llm: Modelo local vía Ollama/LM Studio/vLLM (OpenAI-compatible).

   Tokens OAuth:
   - copilot: obtenido vía `gh auth token`.
   - local_llm: ninguno (endpoint local sin auth por default).
   """
   ```

2. Modificar `invoke()` (línea ~134) para soportar `backend == "local_llm"`:
   ```python
   def invoke(
       *,
       agent_type: str,
       system: str,
       user: str,
       on_log: LogFn,
       execution_id: int | None = None,
       model: str | None = None,
       project_name: str | None = None,
       workspace_root: str | None = None,
       bridge_port: int | None = None,
   ) -> BridgeResponse:
       backend = config.LLM_BACKEND.lower()
       if backend == "mock":
           return _invoke_mock(...)
       if backend == "local_llm":  # Plan 106 F1
           return _invoke_local_llm(
               agent_type=agent_type,
               system=system,
               user=user,
               on_log=on_log,
               execution_id=execution_id,
               model=model or config.LOCAL_LLM_MODEL,
           )
       if backend == "vscode_bridge":
           return _invoke_vscode_bridge(...)
       # ... resto del código (copilot)
   ```

3. Agregar la función `_invoke_local_llm()` (nueva, al final del archivo antes de las funciones
   de vscode_bridge):
   ```python
   def _invoke_local_llm(
       *,
       agent_type: str,
       system: str,
       user: str,
       on_log: LogFn,
       execution_id: int | None = None,
       model: str,
   ) -> BridgeResponse:
       """Invoca un modelo local vía HTTP OpenAI-compatible (Ollama/LM Studio/vLLM).

       Usa LOCAL_LLM_ENDPOINT de config. Si el endpoint no responde, levanta RuntimeError
       con mensaje descriptivo (timeout=30s por default). NO usa auth; si el endpoint requiere
       Bearer token, se puede configurar vía LOCAL_LLM_API_KEY en el futuro (fuera de scope).
       """
       import json

       endpoint = config.LOCAL_LLM_ENDPOINT
       if not endpoint:
           raise RuntimeError(
               "LOCAL_LLM_ENDPOINT no está configurado. Setealo en .env o config.py "
               "(ej. http://localhost:11434/v1/chat/completions para Ollama)."
           )

       headers = {
           "Content-Type": "application/json",
       }
       # Opcional en el futuro: LOCAL_LLM_API_KEY para Bearer auth

       payload = {
           "model": model,
           "messages": [
               {"role": "system", "content": system},
               {"role": "user", "content": user},
           ],
           "stream": False,  # F1: sin streaming por simplicidad (streaming = F4 futuro si hace falta)
       }

       on_log(execution_id, "info", f"Invocando modelo local {model} en {endpoint}")

       try:
           response = requests.post(
               endpoint,
               headers=headers,
               json=payload,
               timeout=30,  # 30s timeout
           )
           if response.status_code != 200:
               body = response.text[:500]
               raise RuntimeError(
                   f"Endpoint local devolvió HTTP {response.status_code}: {body}"
               )

           raw = response.json()
           # Formato OpenAI: {"choices": [{"message": {"content": "..."}}]}
           if "choices" not in raw or not raw["choices"]:
               raise RuntimeError(f"Respuesta del modelo local sin 'choices': {raw[:500]}")

           content = raw["choices"][0].get("message", {}).get("content", "")
           if not content:
               raise RuntimeError("Respuesta del modelo local vacía")

           on_log(execution_id, "info", f"Modelo local respondió con {len(content)} chars")

           return BridgeResponse(
               text=content,
               format="markdown",
               metadata={"model": model, "backend": "local_llm"},
           )

       except requests.Timeout:
           raise RuntimeError(
               f"Endpoint local no respondió en 30s ({endpoint}). "
               "Verificá que Ollama/LLM server esté corriendo."
           )
       except requests.ConnectionError as e:
           raise RuntimeError(
               f"No se pudo conectar al endpoint local ({endpoint}): {e}"
           )
   ```

4. Actualizar `list_copilot_models()` para incluir modelos locales cuando el backend es
   `local_llm` (opcional, pero útil para que el modelo aparezca en la UI):
   ```python
   def list_copilot_models(timeout_sec: int = 15) -> list[dict]:
       backend = config.LLM_BACKEND.lower()
       if backend == "local_llm":
           # Retornar el modelo configurado como único disponible
           return [{
               "id": config.LOCAL_LLM_MODEL,
               "name": f"Modelo local ({config.LOCAL_LLM_MODEL})",
               "vendor": "local",
               "family": "",
               "preview": False,
               "capabilities": {"max_output_tokens": 8192},  # valor estimado Qwen 32B
           }]
       # ... resto del código original (copilot)
   ```

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan106_local_llm_bridge.py` (mockeando `requests.post`):
- `test_f1_local_llm_invoke_success` — mock `requests.post` → 200 con respuesta OpenAI →
  `BridgeResponse` con el content correcto.
- `test_f1_local_llm_invoke_timeout` — mock lanza `Timeout` → `RuntimeError` con hint del timeout.
- `test_f1_local_llm_invoke_connection_error` — mock lanza `ConnectionError` → `RuntimeError` con hint.
- `test_f1_local_llm_invoke_non_200` — mock → 500 → `RuntimeError` con HTTP code.
- `test_f1_local_llm_invoke_missing_choices` — mock → 200 sin `choices` → `RuntimeError`.
- `test_f1_local_llm_invoke_empty_content` — mock → 200 con `content=""` → `RuntimeError`.
- `test_f1_local_llm_list_models_returns_configured_model` — con `LLM_BACKEND="local_llm"`,
  `list_copilot_models()` devuelve 1 dict con el modelo configurado.
- `test_f1_local_llm_endpoint_required` — con `LOCAL_LLM_ENDPOINT=""` → `RuntimeError`.

**Comando:** `cd "Stacky Agents/backend" && venv/Scripts/python.exe -m pytest tests/test_plan106_local_llm_bridge.py -q`

**Criterio binario:** los 8 tests en verde.
**Flag:** consumida en invoke (1).
**Runtimes:** N/A (bridge backend-agnóstico). **Trabajo del operador:** opt-in (configurar vars).

---

### F2 — Integración en llm_router

**Objetivo:** `llm_router.py` reconoce backend `local_llm` y lo despacha correctamente,
incluyéndolo en la lista de modelos disponibles.

**Archivo a EDITAR:** `Stacky Agents/backend/services/llm_router.py`

1. Actualizar docstring para mencionar `local_llm`:
   ```python
   """
   FA-04 — Multi-LLM routing.

   Por agente + complejidad estimada del input, elegir el modelo óptimo.

   Backends soportados:
   - anthropic / mock: Claude Haiku/Sonnet/Opus.
   - copilot: modelos reales habilitados en GitHub Copilot del usuario (consulta `/models`).
   - local_llm: modelo local vía Ollama/LM Studio/vLLM (OpenAI-compatible).
   """
   ```

2. Modificar `_available_models()` (línea ~107) para incluir `local_llm`:
   ```python
   def _available_models() -> list[str]:
       backend = (config.LLM_BACKEND or "mock").lower()
       if backend == "vscode_bridge":
           from copilot_bridge import list_vscode_bridge_models
           live = list_vscode_bridge_models()
           return [m["id"] for m in live]
       if backend == "copilot":
           live = get_copilot_models()
           return [m["id"] for m in live]
       if backend == "local_llm":  # Plan 106 F2
           return [config.LOCAL_LLM_MODEL]
       if backend == "mock":
           return MOCK_MODELS + CLAUDE_MODELS
       return CLAUDE_MODELS + MOCK_MODELS
   ```

3. Modificar `decide()` (línea ~183) para manejar backend `local_llm`:
   ```python
   def decide(
       *,
       agent_type: str,
       blocks: list[dict],
       fingerprint_complexity: str | None = None,
       override: str | None = None,
       backend: str | None = None,
       project_name: str | None = None,
   ) -> RoutingDecision:
       backend = (backend or config.LLM_BACKEND or "anthropic").lower()

       # ... código existente (vscode_bridge health check, mock, override)

       # Plan 106 F2 — local_llm: siempre usar el modelo configurado
       if backend == "local_llm":
           return RoutingDecision(
               model=config.LOCAL_LLM_MODEL,
               reason="backend local_llm (modelo configurado)",
           )

       # ... resto del código (copilot, anthropic)
   ```

4. Actualizar `_pick_copilot_default()` (opcional) para no fallar si no hay modelos
   Copilot pero hay `local_llm`:
   ```python
   def _pick_copilot_default(agent_type: str, available: list[str]) -> str:
       if not available:
           # Si el backend es local_llm, no deberíamos estar acá, pero por seguridad:
           if (config.LLM_BACKEND or "").lower() == "local_llm":
               return config.LOCAL_LLM_MODEL
           # ... resto del código original (raise RuntimeError)
       # ...
   ```

**Tests PRIMERO** — EXTENDER `tests/test_plan106_local_llm_config.py`:
- `test_f2_available_models_includes_local_llm_when_backend_set` — con
  `LLM_BACKEND="local_llm"`, `_available_models()` devuelve `[config.LOCAL_LLM_MODEL]`.
- `test_f2_decide_returns_local_model_when_backend_local_llm` — con `backend="local_llm"`,
  `decide()` devuelve `RoutingDecision` con `model=config.LOCAL_LLM_MODEL` y reason correcto.
- `test_f2_available_models_excludes_local_llm_when_backend_not_set` — con
  `LLM_BACKEND="anthropic"`, `_available_models()` NO incluye `LOCAL_LLM_MODEL`.

**Comando:** `cd "Stacky Agents/backend" && venv/Scripts/python.exe -m pytest tests/test_plan106_local_llm_config.py -q`

**Criterio binario:** los 3 tests nuevos + los 5 de F0 (8 total) en verde.
**Flag:** heredada de F0.
**Runtimes:** backend-agnóstico (los 3 runtimes pueden usarlo). **Trabajo del operador:** opt-in.

---

### F3 — Endpoint /api/llm/analyze-code (análisis de código HITL)

**Objetivo:** endpoint especializado que recibe contexto de código (archivos, proyecto, stack)
y devuelve un análisis markdown del modelo local SIN tool use (solo lectura).

**Archivo NUEVO:** `Stacky Agents/backend/api/local_llm_analysis.py`

```python
"""api/local_llm_analysis.py — Plan 106 F3. Endpoints especializados para modelo local.

POST /api/llm/analyze-code → análisis de código (HITL, sin tools).
POST /api/llm/suggest-pipeline → sugerencias de pipeline (F4).
"""
from __future__ annotations
from flask import Blueprint, jsonify, request

import config as _config

bp = Blueprint("local_llm_analysis", __name__, url_prefix="/llm")

_ANALYZE_ADO_ID = -5  # discriminador (ticket interno, sin ADO real)

def _flag_off() -> bool:
    return not getattr(_config.config, "LOCAL_LLM_ENABLED", False)

def _guard():
    """Guard común: 404 si flag OFF, 400 si POST sin JSON."""
    if _flag_off():
        return jsonify({"error": "local_llm_disabled"}), 404
    if not _config.config.LOCAL_LLM_ENDPOINT:
        return jsonify({"error": "local_llm_endpoint_not_configured"}), 503
    if request.method != "GET" and not request.is_json:
        return jsonify({"error": "body_required_json"}), 400
    return None


@bp.post("/analyze-code", methods=["POST"])
def analyze_code_route():
    """Analiza código con el modelo local (sin tool use).

    Body: {
        "project": str (required),
        "stack": "dotnet" | "node" | "python" | "go" | "rust" | "java" | "php" | "generic" (optional),
        "files": [{"path": str, "content": str}] (optional),
        "prompt": str (optional, pregunta específica del operador)
    }

    Respuesta: {
        "ok": true,
        "analysis": str (markdown),
        "model": str,
        "execution_id": int  # para seguimiento
    }

    El endpoint NO ejecuta tools; inyecta un prompt HITL que prohíbe tool use.
    """
    guard = _guard()
    if guard:
        return guard

    body = request.get_json(silent=True) or {}
    project = body.get("project")
    if not project:
        return jsonify({"error": "project_required"}), 400

    stack = body.get("stack", "generic")
    files = body.get("files", [])
    custom_prompt = body.get("prompt", "")

    # Prompt HITL que prohíbe tools
    system = (
        "Sos un ingeniero senior experto en análisis de código estatico. "
        "Tu UNICA tarea es analizar y explicar en markdown. "
        "\n\n"
        "REGLA ABSOLUTA (HITL):\n"
        "- NUNCA ejecutes comandos.\n"
        "- NUNCA edites archivos.\n"
        "- NUNCA commitees cambios.\n"
        "- NUNCA sugieras comandos que muten el estado del repo.\n"
        "- Solo analizá, explicá y proponé mejoras en texto plano.\n"
    )

    # Armar el contexto de archivos
    files_context = ""
    if files:
        files_context = "\n\n== ARCHIVOS ==\n"
        for f in files:
            path = f.get("path", "")
            content = f.get("content", "")
            files_context += f"\n--- {path} ---\n{content}\n"

    user_prompt = f"""Analizá el código del proyecto "{project}" (stack: {stack}).
{files_context}
Pregunta del operador: {custom_prompt if custom_prompt else "¿Qué observaciones tenés sobre este código?"}

Respondé en markdown con secciones:
1. Hallazgos (bugs, smells, riesgos)
2. Sugerencias (refactors, patrones, mejores prácticas)
3. Preguntas (para el operador)
"""

    # Invocar el modelo local vía copilot_bridge
    from copilot_bridge import invoke
    from db import session_scope
    from models import AgentExecution
    from datetime import datetime

    with session_scope() as session:
        exec_row = AgentExecution(
            ticket_id=None,  # sin ticket
            agent_type="local_llm_analyzer",
            started_at=datetime.utcnow(),
            status="running",
            metadata_dict={
                "backend": "local_llm",
                "model": _config.config.LOCAL_LLM_MODEL,
                "project": project,
                "stack": stack,
            },
        )
        session.add(exec_row)
        session.flush()
        execution_id = exec_row.id

    try:
        response = invoke(
            agent_type="local_llm_analyzer",
            system=system,
            user=user_prompt,
            on_log=lambda eid, level, msg: None,  # sin logging por ahora
            execution_id=execution_id,
            model=_config.config.LOCAL_LLM_MODEL,
        )

        # Marcar como completado
        with session_scope() as session:
            exec_row = session.query(AgentExecution).filter_by(id=execution_id).first()
            if exec_row:
                exec_row.status = "completed"
                exec_row.completed_at = datetime.utcnow()
                exec_row.output = response.text[:10000]  # truncar para la DB
                exec_row.metadata_dict = dict(exec_row.metadata_dict or {})
                exec_row.metadata_dict["backend"] = "local_llm"

        return jsonify({
            "ok": True,
            "analysis": response.text,
            "model": _config.config.LOCAL_LLM_MODEL,
            "execution_id": execution_id,
        })

    except Exception as e:
        with session_scope() as session:
            exec_row = session.query(AgentExecution).filter_by(id=execution_id).first()
            if exec_row:
                exec_row.status = "error"
                exec_row.completed_at = datetime.utcnow()
                exec_row.error_message = str(e)[:500]
        return jsonify({
            "ok": False,
            "error": str(e),
            "execution_id": execution_id,
        }), 502
```

**Registro del blueprint:** en `Stacky Agents/backend/api/__init__.py`:
```python
from .local_llm_analysis import bp as local_llm_analysis_bp  # Plan 106
# ... dentro de register:
api_bp.register_blueprint(local_llm_analysis_bp)
```

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan106_analyze_code_api.py`:
- `test_f3_flag_off_404` — `LOCAL_LLM_ENABLED=False` → 404.
- `test_f3_no_project_400` — body sin `project` → 400.
- `test_f3_no_json_400` — POST form-encoded → 400.
- `test_f3_success_returns_markdown_analysis` — mock `invoke` → devuelve `analysis` markdown.
- `test_f3_invoke_receives_hitl_prompt` — mock `invoke` → verifica que `system` contiene
  "REGLA ABSOLUTA (HITL)" y "NUNCA ejecutes comandos".
- `test_f3_execution_created_and_marked_completed` — mock `invoke` → verifica que se creó
  `AgentExecution` y quedó `status="completed"`.
- `test_f3_error_marks_execution_as_error` — mock `invoke` levanta `Exception` →
  `exec_row.status="error"`.

**Comando:** `cd "Stacky Agents/backend" && venv/Scripts/python.exe -m pytest tests/test_plan106_analyze_code_api.py -q`

**Criterio binario:** los 7 tests en verde.
**Flag:** `LOCAL_LLM_ENABLED` (gate duro 404).
**Runtimes:** backend-agnóstico (endpoint HTTP puro). **Trabajo del operador:** opt-in (flag ON).

---

### F4 — Endpoint /api/llm/suggest-pipeline (sugerencias de pipeline)

**Objetivo:** endpoint especializado que recibe un spec parcial de pipeline (stack, project,
nombre) y devuelve sugerencias de working directory, condition, environment variables SIN tool use.

**Archivo a EDITAR:** `Stacky Agents/backend/api/local_llm_analysis.py` (agregar ruta):

```python
@bp.post("/suggest-pipeline", methods=["POST"])
def suggest_pipeline_route():
    """Sugiere campos de pipeline con el modelo local (sin tool use).

    Body: {
        "project": str (required),
        "stack": "dotnet" | "node" | "python" | "go" | "rust" | "java" | "php" | "generic" (required),
        "spec_partial": dict (optional, el spec parcial del pipeline)
    }

    Respuesta: {
        "ok": true,
        "suggestions": {
            "working_directory": str,
            "condition": str,
            "environment_variables": {key: value},
            "justification": str (markdown)
        },
        "model": str,
        "execution_id": int
    }

    El endpoint NO ejecuta tools; inyecta un prompt HITL que prohíbe tool use.
    """
    guard = _guard()
    if guard:
        return guard

    body = request.get_json(silent=True) or {}
    project = body.get("project")
    stack = body.get("stack")
    if not project or not stack:
        return jsonify({"error": "project_and_stack_required"}), 400

    spec_partial = body.get("spec_partial", {})

    # Prompt HITL
    system = (
        "Sos un ingeniero DevOps senior experto en pipelines CI/CD. "
        "Tu UNICA tarea es sugerir campos de pipeline en formato JSON. "
        "\n\n"
        "REGLA ABSOLUTA (HITL):\n"
        "- NUNCA ejecutes comandos.\n"
        "- NUNCA edites archivos.\n"
        "- NUNCA commitees cambios.\n"
        "- Solo sugerí valores en JSON; el operador los aplicará.\n"
    )

    # Armar el contexto del spec parcial
    spec_context = f"\n\n== SPEC PARCIAL ==\n{json.dumps(spec_partial, ensure_ascii=False, indent=2)}"

    user_prompt = f"""Dado el proyecto "{project}" (stack: {stack}) y el spec parcial:
{spec_context}

Sugerí valores para los siguientes campos del pipeline:
1. working_directory: el directorio de trabajo relativo a la raíz del repo
2. condition: la condición (branch/tag) que dispara el pipeline
3. environment_variables: variables de entorno sugeridas (como dict JSON)

Respondé EXCLUSIVAMENTE en este formato JSON (sin markdown):
{{
    "working_directory": "...",
    "condition": "...",
    "environment_variables": {{"VAR1": "value1", "VAR2": "value2"}},
    "justification": "explicación breve en castellano"
}}

Si no estás seguro, dejá el campo vacío (string vacío o dict vacío).
"""

    # Invocar el modelo local vía copilot_bridge
    from copilot_bridge import invoke
    from db import session_scope
    from models import AgentExecution
    from datetime import datetime
    import json

    with session_scope() as session:
        exec_row = AgentExecution(
            ticket_id=None,
            agent_type="local_llm_pipeline_suggester",
            started_at=datetime.utcnow(),
            status="running",
            metadata_dict={
                "backend": "local_llm",
                "model": _config.config.LOCAL_LLM_MODEL,
                "project": project,
                "stack": stack,
            },
        )
        session.add(exec_row)
        session.flush()
        execution_id = exec_row.id

    try:
        response = invoke(
            agent_type="local_llm_pipeline_suggester",
            system=system,
            user=user_prompt,
            on_log=lambda eid, level, msg: None,
            execution_id=execution_id,
            model=_config.config.LOCAL_LLM_MODEL,
        )

        # Parsear el JSON de la respuesta (el modelo puede devolver markdown con ```json)
        text = response.text.strip()
        if text.startswith("```"):
            # Quitar markdown code block
            text = "\n".join(text.split("\n")[1:-1])
        suggestions = json.loads(text)

        # Marcar como completado
        with session_scope() as session:
            exec_row = session.query(AgentExecution).filter_by(id=execution_id).first()
            if exec_row:
                exec_row.status = "completed"
                exec_row.completed_at = datetime.utcnow()
                exec_row.output = text[:10000]
                exec_row.metadata_dict = dict(exec_row.metadata_dict or {})
                exec_row.metadata_dict["backend"] = "local_llm"

        return jsonify({
            "ok": True,
            "suggestions": suggestions,
            "model": _config.config.LOCAL_LLM_MODEL,
            "execution_id": execution_id,
        })

    except json.JSONDecodeError as e:
        with session_scope() as session:
            exec_row = session.query(AgentExecution).filter_by(id=execution_id).first()
            if exec_row:
                exec_row.status = "error"
                exec_row.completed_at = datetime.utcnow()
                exec_row.error_message = f"JSON parse error: {e}"
        return jsonify({
            "ok": False,
            "error": "json_parse_error",
            "message": "El modelo no devolvió JSON válido",
            "raw_response": response.text[:500],
        }), 502
    except Exception as e:
        with session_scope() as session:
            exec_row = session.query(AgentExecution).filter_by(id=execution_id).first()
            if exec_row:
                exec_row.status = "error"
                exec_row.completed_at = datetime.utcnow()
                exec_row.error_message = str(e)[:500]
        return jsonify({
            "ok": False,
            "error": str(e),
            "execution_id": execution_id,
        }), 502
```

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan106_suggest_pipeline_api.py`:
- `test_f4_flag_off_404` — flag OFF → 404.
- `test_f4_no_project_or_stack_400` — body sin `project` o `stack` → 400.
- `test_f4_success_returns_suggestions_json` — mock `invoke` → devuelve JSON con
  `working_directory`, `condition`, `environment_variables`, `justification`.
- `test_f4_parse_json_strips_markdown_code_blocks` — mock `invoke` → devuelve
  `"```json\n{...}\n```"` → parsea correctamente el JSON interno.
- `test_f4_json_parse_error_502` — mock `invoke` → devuelve texto no-JSON → 502 con
  `error="json_parse_error"`.
- `test_f4_invoke_receives_hitl_prompt` — mock `invoke` → verifica que `system` contiene
  "REGLA ABSOLUTA (HITL)" y "Solo sugerí valores en JSON".

**Comando:** `cd "Stacky Agents/backend" && venv/Scripts/python.exe -m pytest tests/test_plan106_suggest_pipeline_api.py -q`

**Criterio binario:** los 6 tests en verde.
**Flag:** heredada de F0.
**Runtimes:** backend-agnóstico. **Trabajo del operador:** opt-in.

---

### F5 — Frontend: integración UI mínima (opt-in)

**Objetivo:** el modelo local aparece en la UI Arnés (si flag ON) y los 2 endpoints
especializados son accesibles desde una nueva sección "Análisis IA local" o desde las secciones
existentes.

**Archivos:**

1. `Stacky Agents/frontend/src/api/endpoints.ts` — agregar:
   ```ts
   /** Plan 106 — Modelo local (Ollama/LM Studio/vLLM). */
   export const LocalLlmApi = {
     analyzeCode: (body: {
       project: string;
       stack?: string;
       files?: Array<{ path: string; content: string }>;
       prompt?: string;
     }) =>
       api.post<{
       ok: boolean;
       analysis: string;
       model: string;
       execution_id: number;
     }>("/api/llm/analyze-code", body),

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

2. `Stacky Agents/frontend/src/pages/HarnessFlagsPanel.tsx` — verificar que la flag
   `LOCAL_LLM_ENABLED` aparece correctamente (debería aparecer automáticamente por
   `harness_flags.py` si el harness health la expone; si no, agregarla al index signature).

3. (OPCIONAL, fuera de scope v1) `Stacky Agents/frontend/src/components/LocalLlmSection.tsx` —
   componente para probar los endpoints. Para F5 v1, alcanza con que existan los clientes API;
   la UI se puede probar via `curl` o Postman.

**Tests:** sin test de React. Verificación:
- `npx tsc --noEmit` 0 errores.
- Grep: `grep -n "LocalLlmApi" frontend/src/api/endpoints.ts` → ≥2 ocurrencias.

**Criterio binario:** `tsc` 0 err; los greps pasan.
**Flag:** expuesta en health.
**Runtimes:** UI runtime-agnóstica. **Trabajo del operador:** opt-in (flag ON + configuración).

---

### F6 — Cierre: ratchet, export de defaults, doc

**Objetivo:** blindaje e higiene de serie.

1. **Ratchet de tests (plan 49):** agregar los 4 archivos de test backend nuevos a
   `HARNESS_TEST_FILES` en `.sh` y `.ps1`:
   - `test_plan106_local_llm_config.py`
   - `test_plan106_local_llm_bridge.py`
   - `test_plan106_analyze_code_api.py`
   - `test_plan106_suggest_pipeline_api.py`

2. **harness_defaults.env:** NO editar a mano. Dejar constancia en la sección de estado
   de ESTE doc de que la flag nueva nace `false` y que el export
   (`deployment/export_harness_defaults.py`) la incorporará en la próxima corrida del
   operador.

3. **Actualizar encabezado de estado de ESTE doc** al implementar (riel del pipeline).

4. **No-regresión dirigida (por archivo, venv):**
   ```bash
   venv/Scripts/python.exe -m pytest tests/test_llm_router.py tests/test_agent_runner.py tests/test_harness_flags.py -q
   ```

**Criterio binario:** ratchet verde + no-regresión verde.
**Trabajo del operador:** ninguno.

---

## 6. Cómo se honran los 5 KPIs (mapa KPI → mecanismo → test)

| KPI | Mecanismo | Verificación |
|---|---|---|
| **KPI-1 (config)** | 3 vars de entorno (LOCAL_LLM_ENABLED, LOCAL_LLM_ENDPOINT, LOCAL_LLM_MODEL) → modelo aparece | `test_f0_flag_default_off`, `test_f2_available_models_includes_local_llm_when_backend_set` |
| **KPI-2 (análisis código)** | `POST /api/llm/analyze-code` con prompt HITL → markdown sin tools | `test_f3_invoke_receives_hitl_prompt`, `test_f3_success_returns_markdown_analysis` |
| **KPI-3 (creación pipelines)** | `POST /api/llm/suggest-pipeline` con prompt HITL → JSON de sugerencias | `test_f4_success_returns_suggestions_json`, `test_f4_invoke_receives_hitl_prompt` |
| **KPI-4 (paridad 3 runtimes)** | backend `local_llm` es agnóstico; los 3 runtimes pueden usarlo vía `model_override` | `agent_runner.py:219-373` (ruta github_copilot acepta cualquier model_override), F2 tests |
| **KPI-5 (HITL)** | prompts HITL con "REGLA ABSOLUTA: NUNCA ejecutes/NUNCA edites/NUNCA commiteás" | `test_f3_invoke_receives_hitl_prompt`, `test_f4_invoke_receives_hitl_prompt` |

---

## 7. Riesgos y mitigaciones

| Riesgo | Severidad | Mitigación |
|---|---|---|
| El endpoint local (Ollama) no responde | MEDIO | Timeout 30s + `RuntimeError` con hint accionable ("verificá que Ollama esté corriendo") |
| El modelo local ignora el prompt HITL y devuelve tool calls | BAJO | Prompts HITL explícitos + el modelo es read-only por diseño (no se le pasa tool config); riesgo residual aceptado (el operador NO aplica nada sin revisar) |
| El modelo local devuelve JSON inválido en `suggest-pipeline` | BAJO | `json.JSONDecodeError` → 502 con error + raw_response para debug; el operador reintentá |
| La URL del endpoint local está mal configurada | BAJO | Validación en `_invoke_local_llm` → `RuntimeError` con hint ("seteá LOCAL_LLM_ENDPOINT") |
| Costo de tokens del modelo local | BAJO | Es local → costo monetario 0; costo de cómputo lo asume el operador (su máquina) |
| Streaming no soportado en F1 | BAJO | `stream=False` por simplicidad; si hace falta streaming, es F4 futuro fuera de scope |
| El modelo local no es OpenAI-compatible | BAJO | Ollama, LM Studio, vLLM son OpenAI-compatible; si el modelo no lo es, el operador elige otro server |

---

## 8. Fuera de scope

- Streaming de respuestas (F1 usa `stream=False`; streaming = mejora futura).
- Auth con Bearer token para el endpoint local (asumimos `localhost` sin auth; si hace falta,
  `LOCAL_LLM_API_KEY` futuro).
- UI completa para los endpoints (F5 v1 solo clientes API; UI rich = mejora futura).
- Integración con la "memoria que empuja" (planes 48-54) — diferible.
- Casos de uso más allá de análisis de código y pipelines (el operador puede extender).

---

## 9. Glosario

- **backend LLM:** implementación de cómo se invoca un modelo (anthropic, copilot, vscode_bridge,
  local_llm, mock).
- **local_llm:** backend para modelos locales vía endpoint HTTP OpenAI-compatible (Ollama,
  LM Studio, vLLM).
- **OpenAI-compatible:** endpoint que acepta payloads OpenAI (`/v1/chat/completions`,
  `model`, `messages`, `stream`) y responde con `choices[0].message.content`.
- **Ollama:** servidor de LLMs local (https://ollama.com/), default `http://localhost:11434`.
- **LM Studio:** app de serving de LLMs local, OpenAI-compatible.
- **vLLM:** servidor de LLMs de alta performance, OpenAI-compatible.
- **model_override:** parámetro de `agent_runner.run_agent` para forzar un modelo específico.
- **HITL:** Human-in-the-loop. Los endpoints especializados prohíben tools y solo proponen.

---

## 10. Orden de implementación

1. F0 (flag + configuración) — tests → código → verde.
2. F1 (bridge HTTP al modelo local) — tests → código → verde.
3. F2 (integración en llm_router) — tests → código → verde.
4. F3 (endpoint analyze-code) — tests → código → verde.
5. F4 (endpoint suggest-pipeline) — tests → código → verde.
6. F5 (frontend clientes API) — código → tsc 0 err.
7. F6 (ratchet + no-regresión + estado del doc).

---

## 11. Definición de Hecho (DoD)

- [ ] 4 archivos de test backend nuevos verdes (≈26 tests: F0=5, F1=8, F3=7, F4=6)
      corridos POR ARCHIVO con el venv.
- [ ] No-regresión dirigida verde (F6.4).
- [ ] Flag OFF ⇒ 404 en los 2 endpoints especializados (KPI-3/KPI-4 verificados por test).
- [ ] Bridge HTTP funciona con Ollama/LM Studio/vLLM (test mock + verificación manual opcional).
- [ ] Ratchet actualizado en sh y ps1.
- [ ] Commits por fase SOLO con archivos de este plan (jamás `git add -A`).
- [ ] Encabezado de estado de este doc actualizado a IMPLEMENTADO con hashes.
