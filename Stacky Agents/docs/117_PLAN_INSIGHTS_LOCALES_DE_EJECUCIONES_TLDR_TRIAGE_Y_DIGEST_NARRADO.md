# Plan 117 — Insights locales de ejecuciones: TL;DR post-run, triage de fallas y digest narrado (IA local, costo cero)

> **Estado:** PROPUESTO v1 — 2026-07-10
> **Autor:** StackyArchitectaUltraEficientCode
> **Pipeline:** este documento pasó `proponer` (este estado). Sigue `criticar-y-mejorar-plan` → `implementar-plan-stacky` → `supervisar-implementaciones-planes`.
> **Serie:** usos de la IA local (Plan 106 = sustrato modelo local vía Ollama, IMPLEMENTADO; Plan 110 = revisor de PRs con camino solo-local, IMPLEMENTADO; **117 = observabilidad inteligente local**).
> **NO duplica:** 110 (PRs), 112 (retrieval híbrido docs), 113 (Documentador 1-click), 114 (staleness doc↔código), 115 (refactor TF-IDF), 116 (doctor conexiones DETERMINISTA, cero LLM), 104 (doctores IA por sección DevOps). Este plan opera sobre un dominio que ninguno toca: **las ejecuciones de agentes (AgentExecution) y su interpretación**.
> **Depende de:** Plan 106 (ya implementado, commit 344f3124): `copilot_bridge.invoke_local_llm` y flags `LOCAL_LLM_*`. Nada pendiente.

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** Stacky ya registra cada run de agente como `AgentExecution` (los 3 runtimes escriben ahí), pero **nadie interpreta esos registros**: el snapshot de diagnóstico es puro dato crudo (`api/diag.py:44 diagnose_execution`), el digest semanal es un conteo determinista (`services/run_digest.py:10 compose_digest`), y el output/logs de cada run (hasta 10k chars persistidos) quedan sin resumir — el operador lee logs largos o confía a ciegas. Hacer esta interpretación con Claude/Copilot en cada run sería caro, lento y filtraría código privado a la nube. Este plan usa el **modelo local del Plan 106** (costo cero por token, privacidad total, sin cuota) para tres usos de fondo, frecuentes y **visibles en la UI**: **(a) TL;DR post-run** — un barrido de fondo anota cada ejecución terminada con un resumen de 1-3 líneas + etiquetas + nivel de riesgo, visible en la fila del historial (`ExecutionHistoryPage`) y en el drawer de detalle; **(b) triage de fallas** — para runs en `error`/`needs_review`, el mismo insight incluye causa probable, evidencia y siguiente paso sugerido (HITL: sugiere, jamás ejecuta); **(c) digest narrado** — un botón en la `WeeklyDigestCard` existente narra el digest determinista en 5-8 líneas de castellano. Todo detrás de una flag master **OFF por default**, sin crear ejecuciones nuevas (el insight vive en `metadata_json` de la fila ya existente), sin tocar ningún runner y sin degradar nada con la flag OFF.

**KPI / impacto esperado.**
- **Autonomía (binario):** con las flags ON y el modelo local alcanzable, toda ejecución terminada (no excluida) dentro de la ventana gana su insight **sin ninguna acción del operador** (lo garantiza el sweep de fondo; test `test_sweep_annotates_terminated_runs`).
- **Visibilidad (binario):** el TL;DR aparece en la fila del historial, el bloque completo (labels + riesgo + triage) en el drawer de detalle, y la narrativa del digest a un click en la card existente (tests vitest nombrados en F4/F5).
- **Aislamiento (binario):** con la flag master OFF, los payloads de `GET /api/executions/history` y `GET /api/reports/digest` son idénticos a los actuales (campo aditivo `null`/ausente) y se hace **cero** llamada al modelo local (test con `mock.assert_not_called`).
- **Costo cloud cero (binario):** ninguna fase llama a Claude/Copilot; toda inferencia pasa por `copilot_bridge.invoke_local_llm` (grep en el diff: cero referencias nuevas a `invoke_copilot`).

---

## 2. Por qué ahora / gap que cierra

1. **El sustrato local ya existe y está caliente.** Plan 106 dejó `invoke_local_llm(agent_type, system, user, on_log, execution_id, model=None)` (`backend/copilot_bridge.py:190`) que va SIEMPRE al endpoint local ignorando `LLM_BACKEND`, con flags `LOCAL_LLM_ENABLED / LOCAL_LLM_ENDPOINT / LOCAL_LLM_MODEL / LOCAL_LLM_TIMEOUT_SEC` (`backend/services/harness_flags.py:2393-2434`, defaults efectivos en `backend/config.py:80-88`) y endpoints de salud (`api/local_llm_analysis.py:115 local_health_route`). Hoy solo lo consumen análisis puntuales bajo demanda (analyze-code, suggest-pipeline, playground, PR review). **El caso de uso natural del modelo local — tareas de fondo frecuentes y baratas — está sin explotar.**
2. **Las ejecuciones son el dominio con más datos y menos interpretación.** `AgentExecution.metadata_json` (`backend/models.py:219`) ya viaja al frontend en `to_dict()` (`backend/models.py:290`), el historial arma sus items leyendo ese metadata (`backend/api/executions.py:353-373`) y el drawer de detalle carga la ejecución completa (`frontend/src/components/ExecutionDetailDrawer.tsx:36-38` → `Executions.byId`). Anotar el insight en metadata lo hace visible **sin migración de schema y casi sin plomería**.
3. **Usos ya reservados por otros planes quedan intactos.** 116 es explícitamente "cero LLM"; 112-115 son del dominio documental; 110 es PRs. Nada interpreta runs.
4. **Paridad de runtimes gratis por diseño.** Los 3 runtimes (claude_code_cli, codex_cli, github_copilot) persisten en la misma tabla; el runtime es un campo de metadata (`backend/api/executions.py:344`). Un insight post-hoc sobre la fila persistida cubre los 3 sin tocar ningún runner.
5. **El patrón de daemon de fondo ya existe.** `_digest_loop` (`backend/app.py:374-387`) y `_memory_review_sweep_loop` (`backend/app.py:394-409`) son el molde exacto (thread daemon + try/except + sleep).

---

## 3. Principios y guardarraíles (no negociables)

- **3 runtimes con paridad:** el insight se computa desde la fila `AgentExecution` persistida — común a los 3 runtimes. No se toca ningún runner. Fallback: si el modelo local no está alcanzable, el insight queda `state="failed"` con botón manual de regeneración; nada más se degrada.
- **Cero trabajo extra para el operador:** el TL;DR/triage es 100% automático (sweep de fondo); el digest narrado es opt-in por click. Activación: una flag en el panel Arnés existente (`HarnessFlagsPanel`, plan 33/86). Sin pasos manuales nuevos obligatorios.
- **Human-in-the-loop:** el insight **solo anota y sugiere**; jamás ejecuta comandos, edita archivos ni cambia estados de tickets/runs. Los prompts incluyen las reglas HITL (mismas del Plan 106, `api/local_llm_analysis.py:30-37`). El "siguiente paso" del triage es texto para el humano.
- **Mono-operador sin auth:** nada de RBAC; endpoints sin validación de usuario (patrón del repo).
- **Default OFF + UI:** flag master `STACKY_LOCAL_INSIGHTS_ENABLED` default OFF, activable desde la UI del Arnés (el registry de flags ya alimenta el panel). Gotchas obligatorios: FlagSpec nuevas **SIN `default=`** (solo `_CURATED_DEFAULTS_ON` puede; rompe `test_default_known_only_for_curated`, Plan 63); el default **efectivo** vive en `config.py`; `requires` con **profundidad 1** (hijas → master; el master **sin** `requires` estático — la dependencia de `LOCAL_LLM_ENABLED` se chequea en runtime, patrón `_guard()` de `api/local_llm_analysis.py:40-52`) y toda arista nueva se registra en `_REQUIRES_MAP_FROZEN` (`backend/tests/test_harness_flags_requires.py`).
- **No degradar:** el sweep procesa como máximo `MAX_PER_CYCLE` ejecuciones por ciclo, la llamada al LLM ocurre **fuera** de todo `session_scope` (no retiene locks de DB minutos), el daemon nunca propaga excepciones, y con flag OFF el comportamiento es idéntico al actual.
- **Anti-recursión dura:** las ejecuciones generadas por el propio modelo local (`agent_type` que empiece con `local_llm_`, `pr_review_local`, o `metadata.backend == "local_llm"`) **nunca** se anotan; el insight **no crea** filas `AgentExecution` nuevas (desvío consciente del patrón 106 `_create_execution`: crear una ejecución por insight duplicaría el historial y realimentaría al sweep).
- **Ratchet de tests:** todo archivo de test backend nuevo se registra en `backend/scripts/run_harness_tests.sh` y `.ps1` (obligación Plan 49; el meta-test falla si no).

---

## 4. Contrato del insight (congelado)

El insight vive en `AgentExecution.metadata_json` bajo la key `"local_insight"`:

```json
{
  "state": "done",
  "tldr": "string, máx 400 chars, castellano, 1-3 líneas",
  "labels": ["string máx 40 chars", "máximo 5 items"],
  "risk": "low | medium | high",
  "probable_cause": "string máx 500 | null (solo poblado si status era error/needs_review)",
  "evidence": "string máx 500 | null",
  "next_step": "string máx 500 | null",
  "model": "tag del modelo local que lo generó",
  "generated_at": "ISO-8601 UTC",
  "attempts": 1
}
```

Variante de fallo (el modelo no respondió o devolvió basura):

```json
{ "state": "failed", "error": "string máx 300", "attempts": 1, "generated_at": "ISO-8601 UTC", "model": "..." }
```

Reglas: (1) `state` solo `"done"` o `"failed"`; (2) el sweep **no reintenta** filas con la key presente (evita loops contra un modelo caído) — regenerar es acción manual del operador (F3); (3) campos de triage `null` cuando el run terminó `completed`; (4) el objeto completo serializado no supera ~1.5 KB (los caps de longitud lo garantizan).

---

## 5. Fases

### F0 — Flags del arnés + defaults en config (sustrato de configuración)

**Objetivo:** dar de alta las 5 flags del plan, visibles y editables en el panel Arnés, default OFF, sin romper ningún test curado.

**Archivos a editar:**
- `Stacky Agents/backend/services/harness_flags.py`
- `Stacky Agents/backend/config.py`
- `Stacky Agents/backend/services/harness_flags_help.py`
- `Stacky Agents/backend/tests/test_harness_flags_requires.py` (solo el mapa congelado)

**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan117_insights_flags.py`

**Cambios exactos:**

1. En `harness_flags.py`, después del bloque Plan 110 (buscar el comentario `# ── Plan 110 — Revisor de PRs`, la última FlagSpec de ese bloque), agregar al `FLAG_REGISTRY`:

```python
    # ── Plan 117 — Insights locales de ejecuciones (TL;DR + triage + digest narrado) ──
    FlagSpec(
        key="STACKY_LOCAL_INSIGHTS_ENABLED",
        type="bool",
        label="Insights locales de ejecuciones",
        description="TL;DR y triage automáticos de cada run terminado usando el modelo local (Plan 106). Requiere el modelo local habilitado y configurado.",
        group="global",
        # SIN default= (no curada en _CURATED_DEFAULTS_ON; el default efectivo OFF vive en config.py — gotcha Plan 63/81).
        # SIN requires= estático hacia LOCAL_LLM_ENABLED: la dependencia se chequea en runtime
        # (R4 prohíbe cadenas: las hijas de abajo ya consumen la única arista permitida).
    ),
    FlagSpec(
        key="STACKY_LOCAL_INSIGHTS_SWEEP_SEC",
        type="int",
        label="Intervalo del sweep de insights (segundos)",
        description="Cada cuántos segundos el barrido de fondo busca ejecuciones terminadas sin insight.",
        group="global",
        requires="STACKY_LOCAL_INSIGHTS_ENABLED",
        min_value=30,
        max_value=3600,
        # SIN default= (mismo motivo que LOCAL_LLM_ENDPOINT, harness_flags.py:2411-2413).
    ),
    FlagSpec(
        key="STACKY_LOCAL_INSIGHTS_MAX_PER_CYCLE",
        type="int",
        label="Máximo de insights por ciclo",
        description="Tope de ejecuciones anotadas por ciclo del barrido (protege la CPU/GPU local).",
        group="global",
        requires="STACKY_LOCAL_INSIGHTS_ENABLED",
        min_value=1,
        max_value=20,
    ),
    FlagSpec(
        key="STACKY_LOCAL_INSIGHTS_LOOKBACK_DAYS",
        type="int",
        label="Ventana de insights (días)",
        description="Solo se anotan ejecuciones iniciadas dentro de esta ventana hacia atrás.",
        group="global",
        requires="STACKY_LOCAL_INSIGHTS_ENABLED",
        min_value=1,
        max_value=90,
    ),
    FlagSpec(
        key="STACKY_LOCAL_INSIGHTS_DIGEST_NARRATIVE_ENABLED",
        type="bool",
        label="Narrativa local del digest",
        description="Habilita narrar el digest de ejecuciones en lenguaje natural con el modelo local (botón en la card del digest).",
        group="global",
        requires="STACKY_LOCAL_INSIGHTS_ENABLED",
    ),
```

2. En `harness_flags.py`, agregar las 5 keys a `_CATEGORY_KEYS["avanzado"]` (`harness_flags.py:245-250`, misma tupla donde viven las `LOCAL_LLM_*`; la nota de `harness_flags.py:254-255` avisa que `test_every_registry_flag_is_categorized` rompe si no).

3. En `config.py`, inmediatamente después del bloque `LOCAL_LLM_*` (`config.py:80-88`), agregar (copiando el patrón booleano EXACTO de `LOCAL_LLM_ENABLED` en `config.py:81-83`, pero con default `"false"`):

```python
    # Plan 117 — Insights locales de ejecuciones. Default OFF (el operador activa por UI).
    STACKY_LOCAL_INSIGHTS_ENABLED = os.getenv("STACKY_LOCAL_INSIGHTS_ENABLED", "false").lower() in (
        "1", "true", "yes",
    )
    STACKY_LOCAL_INSIGHTS_SWEEP_SEC = int(os.getenv("STACKY_LOCAL_INSIGHTS_SWEEP_SEC", "180"))
    STACKY_LOCAL_INSIGHTS_MAX_PER_CYCLE = int(os.getenv("STACKY_LOCAL_INSIGHTS_MAX_PER_CYCLE", "3"))
    STACKY_LOCAL_INSIGHTS_LOOKBACK_DAYS = int(os.getenv("STACKY_LOCAL_INSIGHTS_LOOKBACK_DAYS", "7"))
    STACKY_LOCAL_INSIGHTS_DIGEST_NARRATIVE_ENABLED = os.getenv(
        "STACKY_LOCAL_INSIGHTS_DIGEST_NARRATIVE_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
```

   Nota: si el patrón booleano real de `config.py:81-83` difiere en la tupla de valores aceptados, copiar EL DEL ARCHIVO (manda el código, no este doc).

4. En `harness_flags_help.py`, agregar una entrada de ayuda por cada una de las 5 flags copiando el formato exacto de las entradas `LOCAL_LLM_*` existentes en ese archivo (mismo shape de dict/texto; buscarlas con grep `LOCAL_LLM_` dentro del archivo).

5. En `tests/test_harness_flags_requires.py`, agregar al mapa congelado `_REQUIRES_MAP_FROZEN` las 4 aristas nuevas (formato del mapa tal cual está en el archivo):
   - `STACKY_LOCAL_INSIGHTS_SWEEP_SEC` → `STACKY_LOCAL_INSIGHTS_ENABLED`
   - `STACKY_LOCAL_INSIGHTS_MAX_PER_CYCLE` → `STACKY_LOCAL_INSIGHTS_ENABLED`
   - `STACKY_LOCAL_INSIGHTS_LOOKBACK_DAYS` → `STACKY_LOCAL_INSIGHTS_ENABLED`
   - `STACKY_LOCAL_INSIGHTS_DIGEST_NARRATIVE_ENABLED` → `STACKY_LOCAL_INSIGHTS_ENABLED`

**Tests (TDD — escribirlos ANTES de tocar el registry), `tests/test_plan117_insights_flags.py`:**
- `test_flags_registered`: las 5 keys existen en el registry (`get_flag_specs()` o el símbolo público equivalente que usen los tests de flags existentes — copiar el patrón de `test_plan106_local_llm_config.py`).
- `test_master_has_no_requires`: la FlagSpec `STACKY_LOCAL_INSIGHTS_ENABLED` tiene `requires` vacío/None.
- `test_children_require_master`: las otras 4 tienen `requires == "STACKY_LOCAL_INSIGHTS_ENABLED"`.
- `test_numeric_bounds`: SWEEP_SEC (30, 3600), MAX_PER_CYCLE (1, 20), LOOKBACK_DAYS (1, 90) — `min_value`/`max_value` exactos.
- `test_no_explicit_default_on_new_flags`: ninguna de las 5 FlagSpec declara `default=` (introspección igual que hace `test_default_known_only_for_curated`).
- `test_config_defaults_off`: con env limpio (monkeypatch.delenv de las 5 keys, `raising=False`) y releyendo config (mismo mecanismo de reload que usa `test_plan106_local_llm_config.py`), `STACKY_LOCAL_INSIGHTS_ENABLED` es False, SWEEP_SEC==180, MAX_PER_CYCLE==3, LOOKBACK_DAYS==7, DIGEST_NARRATIVE False.

**Comandos de verificación (binarios):**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests\test_plan117_insights_flags.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_harness_flags.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_harness_flags_requires.py -q
```
**Criterio de aceptación:** los 3 comandos terminan en verde (0 failed). NOTA: `test_harness_flags.py` tiene fallas preexistentes SOLO si el checkout arrastra el drift de `harness_defaults.env` (memoria del repo); el criterio es "cero fallas NUEVAS respecto a correr el mismo archivo en HEAD antes del cambio" — comparar ambas corridas.

**Flag protectora:** son las flags mismas. Default seguro: OFF.
**Impacto por runtime:** ninguno directo (solo registry/config). Paridad N/A.
**Trabajo del operador:** ninguno (activación futura opt-in por UI).

---

### F1 — Núcleo puro `services/local_insights.py` (prompts, parseo, elegibilidad)

**Objetivo:** toda la lógica determinista del insight como funciones puras testeables sin red ni DB.

**Archivo a crear:** `Stacky Agents/backend/services/local_insights.py`
**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan117_insights_core.py`

**Símbolos exactos (módulo nuevo):**

```python
"""services/local_insights.py — Plan 117. Insights locales de ejecuciones (IA local, Plan 106).

Núcleo puro: elegibilidad, construcción de prompts, parseo defensivo.
La persistencia y el sweep viven en este mismo módulo (F2) pero separados
de las funciones puras para que los tests de F1 no toquen DB ni red.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

INSIGHT_KEY = "local_insight"

# Anti-recursión: ejecuciones producidas por el propio modelo local jamás se anotan.
EXCLUDED_AGENT_TYPES = frozenset({
    "local_llm_analyzer",        # Plan 106 analyze-code
    "local_llm_pipeline_suggester",  # Plan 106 suggest-pipeline
    "local_llm_playground",      # Plan 106 playground
    "pr_review_local",           # Plan 110 camino solo-local
    "local_insights",            # este plan (defensa extra)
})

# Estados que ganan insight. "cancelled" queda FUERA (el operador ya sabe por qué canceló).
TERMINAL_INSIGHT_STATUSES = frozenset({"completed", "error", "needs_review"})

# Caps del contrato §4.
TLDR_MAX = 400
LABEL_MAX = 40
LABELS_MAX_COUNT = 5
TRIAGE_FIELD_MAX = 500
ERROR_MAX = 300
NARRATIVE_MAX = 1200

# Truncado de inputs al prompt (el modelo local tiene contexto acotado).
OUTPUT_HEAD_CHARS = 3000
OUTPUT_TAIL_CHARS = 3000
INPUT_CONTEXT_MAX = 1500

HITL_RULES = (
    "\n\nREGLA ABSOLUTA (HITL):\n"
    "- NUNCA ejecutes comandos.\n"
    "- NUNCA edites archivos.\n"
    "- NUNCA commitees cambios.\n"
    "- NUNCA sugieras comandos que muten el estado del repo.\n"
    "- Solo analizá, explicá y proponé; el operador humano decide qué aplicar.\n"
)
```

Funciones puras (firmas y comportamiento exactos):

1. `truncate_middle(text: str, head: int = OUTPUT_HEAD_CHARS, tail: int = OUTPUT_TAIL_CHARS) -> str`
   - Si `len(text) <= head + tail + 40` devuelve `text` tal cual; si no, `text[:head] + "\n... [recortado] ...\n" + text[-tail:]`.

2. `execution_view(row) -> dict`
   - Convierte una fila `AgentExecution` (o un objeto con los mismos atributos) al dict mínimo del dominio:
     `{"id", "agent_type", "status", "error_message", "output", "input_context_json", "started_at", "completed_at", "metadata"}` — `metadata` = `row.metadata_dict or {}`; fechas como objetos datetime o None; strings o "".
   - Es el ÚNICO punto donde el resto del módulo toca el ORM; todo lo demás opera sobre este dict (testeable con dicts literales).

3. `is_eligible(view: dict) -> tuple[bool, str]`
   - Reglas duras (independientes de si ya hay insight): status ∈ `TERMINAL_INSIGHT_STATUSES` (si no → `(False, "status_not_terminal")`); `agent_type` ∉ `EXCLUDED_AGENT_TYPES` y no empieza con `"local_llm_"` (→ `(False, "agent_type_excluded")`); `view["metadata"].get("backend") != "local_llm"` (→ `(False, "local_llm_backend_excluded")`). Si pasa todo → `(True, "ok")`.

4. `should_sweep(view: dict) -> tuple[bool, str]`
   - `is_eligible` y además `INSIGHT_KEY not in view["metadata"]` (si presente → `(False, "already_has_insight")`). El sweep NO reintenta `failed` (regla §4.2).

5. `build_insight_prompt(view: dict) -> tuple[str, str]`
   - Devuelve `(system, user)`.
   - `system` = "Sos un ingeniero senior que audita ejecuciones de agentes de IA. Tu ÚNICA tarea es resumir y diagnosticar en JSON estricto." + `HITL_RULES`.
   - `user` incluye, en este orden y con estos rótulos literales: `== EJECUCIÓN ==` (id, agent_type, status, duración en segundos si ambas fechas existen, runtime de `metadata.get("runtime")`), `== CONTEXTO DE ENTRADA (recortado) ==` (`input_context_json` truncado a `INPUT_CONTEXT_MAX`), `== OUTPUT (recortado) ==` (`truncate_middle(output)`), y si status != "completed": `== ERROR ==` (`error_message` completo hasta 2000 chars).
   - Instrucción de salida literal en el prompt:
     `Respondé EXCLUSIVAMENTE con un objeto JSON (sin markdown) con las keys: {"tldr": "resumen en castellano de 1-3 líneas", "labels": ["hasta 5 etiquetas cortas"], "risk": "low|medium|high", "probable_cause": "...", "evidence": "...", "next_step": "..."}. Si el status es completed, poné null en probable_cause, evidence y next_step.`

6. `parse_insight_response(text: str) -> dict`
   - Quita fences markdown si empieza con "```" (mismo bloque de 4 líneas de `api/local_llm_analysis.py:324-327`).
   - `json.loads`; si falla → `raise ValueError(f"json_parse_error: {e}")`.
   - Normaliza y capa: `tldr` obligatorio str no vacío (si falta/vacío → `raise ValueError("tldr_missing")`), recortado a `TLDR_MAX`; `labels` → lista de str no vacíos, cada uno recortado a `LABEL_MAX`, máximo `LABELS_MAX_COUNT` (cualquier otra cosa → `[]`); `risk` ∈ {"low","medium","high"} si no → `"low"`; `probable_cause`/`evidence`/`next_step` → str recortado a `TRIAGE_FIELD_MAX` o `None`.
   - Devuelve SOLO esas 6 keys.

7. `make_insight_metadata(parsed: dict, *, model: str, attempts: int) -> dict`
   - Devuelve `{**parsed, "state": "done", "model": model, "generated_at": <ISO UTC con sufijo Z>, "attempts": attempts}` (contrato §4).

8. `build_digest_narrative_prompt(digest: dict) -> tuple[str, str]` (lo consume F5)
   - `system` = "Sos un analista técnico. Narrás métricas de ejecuciones de agentes en castellano claro, sin inventar datos." + `HITL_RULES`.
   - `user` = JSON compacto de `digest["totals"]`, `digest["by_agent_type"]`, `digest["by_runtime"]`, `digest["top_failures"]`, `digest["highlights"]` (usar `.get(...)` con defaults vacíos; el shape viene de `services/run_digest.py:10 compose_digest`) + instrucción literal: `Escribí un resumen narrativo de entre 5 y 8 líneas, en texto plano (sin markdown, sin listas), mencionando totales, tasa de éxito, el agente más activo y las fallas más repetidas si las hay. No inventes números que no estén en los datos.`

**Tests (TDD), `tests/test_plan117_insights_core.py`** (sin DB, sin red — solo dicts):
- `test_truncate_middle_short_passthrough` / `test_truncate_middle_long_keeps_head_and_tail` (contiene el marcador `[recortado]` y los extremos).
- `test_is_eligible_ok` (developer/completed → True).
- `test_is_eligible_rejects_running` (`status_not_terminal`).
- `test_is_eligible_rejects_cancelled` (cancelled NO gana insight).
- `test_is_eligible_rejects_local_llm_agent_types` (cada uno de `EXCLUDED_AGENT_TYPES` y un `local_llm_lo_que_sea` por prefijo).
- `test_is_eligible_rejects_backend_local_llm` (metadata backend="local_llm").
- `test_should_sweep_skips_existing_insight` (metadata con `local_insight` → False, "already_has_insight"; incluye el caso `state="failed"`).
- `test_build_prompt_completed_has_no_error_section` (sin `== ERROR ==` y pide null en triage).
- `test_build_prompt_error_includes_error_message` (con `== ERROR ==` y el texto del error).
- `test_parse_valid_json` / `test_parse_strips_fences` / `test_parse_invalid_json_raises` / `test_parse_missing_tldr_raises` / `test_parse_caps_labels_and_lengths` (7 labels de 100 chars → 5 de ≤40) / `test_parse_bad_risk_defaults_low`.
- `test_make_insight_metadata_contract` (keys exactas del §4, state done, generated_at termina en "Z").

**Comando:** `.\.venv\Scripts\python.exe -m pytest tests\test_plan117_insights_core.py -q`
**Criterio:** verde (0 failed).
**Flag:** N/A (código puro sin efectos; nada lo invoca todavía).
**Impacto por runtime:** N/A (puro).
**Trabajo del operador:** ninguno.

---

### F2 — Persistencia + sweep de fondo (el TL;DR aparece solo)

**Objetivo:** un barrido de fondo anota las ejecuciones terminadas sin insight, con topes, gates de flags y anti-recursión.

**Archivos a editar:**
- `Stacky Agents/backend/services/local_insights.py` (agregar la capa con efectos)
- `Stacky Agents/backend/app.py` (armar el daemon)

**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan117_insights_sweep.py`

**Cambios exactos en `services/local_insights.py`:**

```python
def pick_candidates(session, *, lookback_days: int, limit: int) -> list:
    """Filas terminadas recientes sin insight, más recientes primero.

    El filtro SQL grueso usa LIKE sobre metadata_json (portable en SQLite);
    OJO: metadata_json puede ser NULL → hay que aceptar NULL explícitamente
    (NOT LIKE sobre NULL da NULL y excluiría filas vírgenes).
    El filtro fino (exclusiones §3) lo hace should_sweep en Python.
    """
    from sqlalchemy import or_
    from models import AgentExecution

    cutoff = datetime.utcnow() - timedelta(days=max(1, lookback_days))
    rows = (
        session.query(AgentExecution)
        .filter(AgentExecution.status.in_(sorted(TERMINAL_INSIGHT_STATUSES)))
        .filter(AgentExecution.completed_at.isnot(None))
        .filter(AgentExecution.started_at >= cutoff)
        .filter(or_(
            AgentExecution.metadata_json.is_(None),
            ~AgentExecution.metadata_json.contains('"local_insight"'),
        ))
        .order_by(AgentExecution.completed_at.desc())
        .limit(max(1, limit) * 4)   # margen para el filtro fino en Python
        .all()
    )
    keep = [r for r in rows if should_sweep(execution_view(r))[0]]
    return keep[: max(1, limit)]


def _write_insight(execution_id: int, insight: dict) -> None:
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return
        md = row.metadata_dict or {}
        md[INSIGHT_KEY] = insight
        row.metadata_dict = md   # setter serializa (models.py:263-265)


def generate_insight_for_execution(execution_id: int, *, force: bool = False) -> dict:
    """Genera y persiste el insight de UNA ejecución. Nunca lanza: devuelve {"ok": bool, ...}.

    La llamada al LLM ocurre FUERA de session_scope (puede tardar minutos;
    no se retienen locks de DB).
    """
    import config as _config
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return {"ok": False, "error": "execution_not_found"}
        view = execution_view(row)

    eligible, reason = is_eligible(view)
    if not eligible:
        return {"ok": False, "error": "insight_excluded", "reason": reason}
    existing = view["metadata"].get(INSIGHT_KEY)
    if existing and not force:
        return {"ok": True, "insight": existing, "cached": True}

    prev_attempts = int((existing or {}).get("attempts") or 0)
    system, user = build_insight_prompt(view)
    model_cfg = getattr(_config.config, "LOCAL_LLM_MODEL", "")

    from copilot_bridge import invoke_local_llm  # import lazy (patrón del repo)
    try:
        resp = invoke_local_llm(
            agent_type="local_insights",
            system=system,
            user=user,
            on_log=lambda level, msg: None,   # firma LogFn real (level, msg) — gotcha Plan 106 C3
            execution_id=execution_id,
        )
        parsed = parse_insight_response(resp.text)
        insight = make_insight_metadata(
            parsed,
            model=(getattr(resp, "metadata", None) or {}).get("model") or model_cfg,
            attempts=prev_attempts + 1,
        )
        _write_insight(execution_id, insight)
        return {"ok": True, "insight": insight}
    except Exception as e:  # noqa: BLE001 — el sweep jamás debe morir por una fila
        insight = {
            "state": "failed",
            "error": str(e)[:ERROR_MAX],
            "attempts": prev_attempts + 1,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "model": model_cfg,
        }
        _write_insight(execution_id, insight)
        return {"ok": False, "error": "generation_failed", "insight": insight}


def run_sweep_once() -> int:
    """Un ciclo del barrido. Devuelve cuántas ejecuciones quedaron anotadas OK.

    Gates (en este orden, todos hot — mismos getattr que usa api/local_llm_analysis.py:41):
    master OFF → 0; LOCAL_LLM_ENABLED OFF → 0; LOCAL_LLM_ENDPOINT vacío → 0.
    """
    import config as _config
    from db import session_scope

    cfg = _config.config
    if not getattr(cfg, "STACKY_LOCAL_INSIGHTS_ENABLED", False):
        return 0
    if not getattr(cfg, "LOCAL_LLM_ENABLED", False):
        return 0
    if not getattr(cfg, "LOCAL_LLM_ENDPOINT", ""):
        return 0
    limit = max(1, int(getattr(cfg, "STACKY_LOCAL_INSIGHTS_MAX_PER_CYCLE", 3)))
    lookback = max(1, int(getattr(cfg, "STACKY_LOCAL_INSIGHTS_LOOKBACK_DAYS", 7)))

    with session_scope() as session:
        candidate_ids = [r.id for r in pick_candidates(session, lookback_days=lookback, limit=limit)]

    done = 0
    for eid in candidate_ids:
        if generate_insight_for_execution(eid).get("ok"):
            done += 1
    return done
```

**Cambio exacto en `app.py`:** inmediatamente después del bloque M0.3 (`_memory_review_sweep_loop`, `app.py:394-409` — insertar tras el `threading.Thread(...).start()` + `logger.info` de ese bloque), copiando su patrón:

```python
    # ── Plan 117 — Sweep de insights locales (TL;DR/triage con el modelo local) ──
    # El thread arranca SIEMPRE; los gates (flags) se evalúan en cada iteración
    # dentro de run_sweep_once() → hot-apply real, sin restart_required.
    def _local_insights_sweep_loop() -> None:
        from services import local_insights

        while True:
            try:
                processed = local_insights.run_sweep_once()
                if processed:
                    logger.info("local insights sweep: %d ejecuciones anotadas", processed)
            except Exception:
                logger.exception("local insights sweep daemon falló")
            try:
                interval = int(getattr(config, "STACKY_LOCAL_INSIGHTS_SWEEP_SEC", 180))
            except (TypeError, ValueError):
                interval = 180
            time.sleep(max(30, interval))

    threading.Thread(
        target=_local_insights_sweep_loop,
        name="stacky-local-insights-daemon",
        daemon=True,
    ).start()
    logger.info("local insights daemon armed")
```

   Usar las referencias `config`, `threading`, `time`, `logger` YA importadas/definidas en `app.py` (las mismas que usan `_digest_loop` y `_memory_review_sweep_loop`). Si el bloque M0.3 está condicionado por una flag, el bloque nuevo va FUERA de esa condición (arranca siempre).

**Tests (TDD), `tests/test_plan117_insights_sweep.py`** — usar la misma infraestructura de DB temporal/fixture que usan los tests existentes que crean `AgentExecution` (copiar el setup de `test_plan106_analyze_code_api.py`, que ya resuelve app+DB). Mock SIEMPRE en módulo origen: `mock.patch("copilot_bridge.invoke_local_llm", ...)` (gotcha documentado en `test_plan106_analyze_code_api.py:4-5`). Para las flags: `monkeypatch.setattr(config.config, "STACKY_LOCAL_INSIGHTS_ENABLED", True, raising=False)` etc.
- `test_sweep_annotates_terminated_runs` (**KPI central**): 2 ejecuciones `completed` recientes sin insight + flags ON + mock que devuelve `{"tldr": "ok", "labels": ["x"], "risk": "low", "probable_cause": null, "evidence": null, "next_step": null}` → `run_sweep_once() == 2` y ambas filas tienen `metadata_dict["local_insight"]["state"] == "done"` y `tldr == "ok"`.
- `test_sweep_master_off_makes_zero_calls`: master OFF → `run_sweep_once() == 0` y `mock.assert_not_called()`.
- `test_sweep_requires_local_llm_enabled`: master ON pero `LOCAL_LLM_ENABLED=False` → 0 llamadas.
- `test_sweep_skips_excluded_agent_types`: una ejecución `local_llm_playground` completed → no se anota.
- `test_sweep_skips_rows_with_insight`: fila con `local_insight` presente (incluido `state="failed"`) → no se re-procesa.
- `test_sweep_respects_max_per_cycle`: 5 candidatas, `MAX_PER_CYCLE=2` → mock llamado exactamente 2 veces.
- `test_generate_failure_writes_failed_state`: mock lanza `RuntimeError("boom")` → resultado `ok=False`, metadata queda `state="failed"`, `error` contiene "boom", `attempts == 1`.
- `test_generate_force_regenerates`: fila con insight `done` + `force=True` → mock SÍ se llama y `attempts` incrementa a 2.
- `test_pick_candidates_includes_null_metadata`: fila con `metadata_json` NULL entra como candidata (regresión del gotcha NOT-LIKE-NULL).

**Comando:** `.\.venv\Scripts\python.exe -m pytest tests\test_plan117_insights_sweep.py -q`
**Criterio:** verde (0 failed).
**Flag protectora:** `STACKY_LOCAL_INSIGHTS_ENABLED` (OFF ⇒ el daemon existe pero cada ciclo devuelve 0 sin tocar red ni DB de escritura).
**Impacto por runtime:** anota ejecuciones de los 3 runtimes por igual (opera sobre la tabla común). Fallback: modelo local caído → `state="failed"` una sola vez por fila, sin loops.
**Trabajo del operador:** ninguno (todo de fondo).

---

### F3 — API: insight visible en el historial + regeneración bajo demanda

**Objetivo:** exponer el insight en el payload del historial (campo aditivo) y dar un endpoint HITL para generar/regenerar el insight de UNA ejecución.

**Archivos a editar:**
- `Stacky Agents/backend/api/executions.py`
- `Stacky Agents/backend/api/local_llm_analysis.py`

**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan117_insights_api.py`

**Cambios exactos:**

1. `api/executions.py` — en el item del historial (`executions.py:353-373`), después de la línea `"error_message": row.error_message or None,` agregar:

```python
                "local_insight": meta.get("local_insight") or None,  # Plan 117 (aditivo)
```

   (`GET /api/executions/<id>` NO necesita cambios: `to_dict()` ya incluye `"metadata"` completo, `models.py:290`.)

2. `api/local_llm_analysis.py` — agregar al final del archivo:

```python
@bp.post("/insights/<int:execution_id>/generate")
def generate_insight_route(execution_id: int):
    """Plan 117 — Genera/regenera el insight local de UNA ejecución (acción HITL del operador).

    Ruta final: POST /api/llm/insights/<id>/generate (blueprint url_prefix="/llm").
    404 flag master OFF | 404 execution inexistente | 409 excluida | 502 fallo del modelo.
    """
    guard = _guard()   # 404 LOCAL_LLM_ENABLED OFF / 503 endpoint vacío (api/local_llm_analysis.py:40-52)
    if guard:
        return guard
    if not getattr(_config.config, "STACKY_LOCAL_INSIGHTS_ENABLED", False):
        return jsonify({"error": "local_insights_disabled"}), 404

    from services.local_insights import generate_insight_for_execution

    result = generate_insight_for_execution(execution_id, force=True)
    if result.get("ok"):
        return jsonify(result)
    err = result.get("error")
    if err == "execution_not_found":
        return jsonify(result), 404
    if err == "insight_excluded":
        return jsonify(result), 409
    return jsonify(result), 502
```

**Tests (TDD), `tests/test_plan117_insights_api.py`** (mismo setup de app/DB que F2; client Flask de test):
- `test_generate_endpoint_master_off_404`: `LOCAL_LLM_ENABLED=True` pero insights OFF → 404 `local_insights_disabled`.
- `test_generate_endpoint_local_llm_off_404`: `LOCAL_LLM_ENABLED=False` → 404 (via `_guard`).
- `test_generate_endpoint_ok`: flags ON + mock (`copilot_bridge.invoke_local_llm`) → 200, body `ok=True` con `insight.tldr`, y la fila queda anotada.
- `test_generate_endpoint_excluded_409`: ejecución `local_llm_playground` → 409 `insight_excluded`.
- `test_generate_endpoint_not_found_404`: id inexistente → 404 `execution_not_found`.
- `test_generate_endpoint_model_failure_502`: mock lanza → 502 y metadata `state="failed"`.
- `test_history_includes_local_insight`: con `STACKY_EXECUTION_HISTORY_ENABLED=true` (env, gate de `executions.py:287`), una fila anotada devuelve el objeto en `local_insight` y una sin anotar devuelve `null`.
- `test_history_shape_unchanged_when_flag_off`: master OFF y fila sin insight → el item tiene `local_insight: null` y TODAS las demás keys idénticas a las de hoy (comparar contra el set literal de keys de `executions.py:353-373` + la nueva).

**Comando:** `.\.venv\Scripts\python.exe -m pytest tests\test_plan117_insights_api.py -q`
**Criterio:** verde (0 failed).
**Flag protectora:** `STACKY_LOCAL_INSIGHTS_ENABLED` (+ `_guard()` hereda el gate de `LOCAL_LLM_ENABLED`).
**Impacto por runtime:** endpoint agnóstico del runtime de la ejecución (los 3 por igual).
**Trabajo del operador:** ninguno (el endpoint manual es opcional).

---

### F4 — UI: TL;DR en el historial + bloque de insight en el drawer

**Objetivo:** que el operador VEA el insight sin abrir logs: línea TL;DR en cada fila del historial y bloque completo (labels, riesgo, triage, botón regenerar) en el drawer de detalle.

**Archivos a editar:**
- `Stacky Agents/frontend/src/api/endpoints.ts`
- `Stacky Agents/frontend/src/pages/ExecutionHistoryPage.tsx` (+ su `ExecutionHistoryPage.module.css`)
- `Stacky Agents/frontend/src/components/ExecutionDetailDrawer.tsx`

**Archivos a crear:**
- `Stacky Agents/frontend/src/components/ExecutionInsightBlock.tsx`
- `Stacky Agents/frontend/src/components/ExecutionInsightBlock.module.css`
- `Stacky Agents/frontend/src/components/__tests__/ExecutionInsightBlock.test.tsx`

**PRECAUCIÓN GIT:** NO tocar `ActiveRunsPanel.tsx` ni ningún archivo bajo `frontend/src/components/devops/` (arrastran WIP de otra sesión). Las superficies elegidas están limpias.

**Cambios exactos:**

1. `endpoints.ts`:
   - Exportar el tipo:
     ```ts
     export interface ExecutionLocalInsight {
       state: "done" | "failed";
       tldr?: string;
       labels?: string[];
       risk?: "low" | "medium" | "high";
       probable_cause?: string | null;
       evidence?: string | null;
       next_step?: string | null;
       model?: string;
       generated_at?: string;
       attempts?: number;
       error?: string;
     }
     ```
   - En `ExecutionHistoryItem` agregar `local_insight?: ExecutionLocalInsight | null;`.
   - En el objeto de wrappers donde viven los llamados a `/llm/...` (buscar el que usa `LocalLlmPlaygroundPanel.tsx`; si no existe un grupo `LocalLlm`, agregar el método dentro del grupo `Executions`): `generateInsight: (executionId: number) => post(`/llm/insights/${executionId}/generate`, {})` usando el helper HTTP existente del archivo (mismo `post`/`request` que usan los demás wrappers).

2. `ExecutionInsightBlock.tsx` (componente nuevo, presentacional + acción):
   - Props: `{ executionId: number; insight: ExecutionLocalInsight | null | undefined; onRegenerated?: () => void }`.
   - Render:
     - Título de sección: `Insight (IA local)`.
     - Si `insight?.state === "done"`: párrafo `tldr`; chips de `labels`; badge de `risk` con clases `riskLow|riskMedium|riskHigh`; si `probable_cause || evidence || next_step`: sub-bloque "Triage" con tres filas rotuladas `Causa probable / Evidencia / Siguiente paso sugerido`; pie chico `generated_at + model`.
     - Si `insight?.state === "failed"`: texto `No se pudo generar el insight` + `insight.error` + botón `Reintentar`.
     - Si `insight` es null/undefined: botón `Generar insight (IA local)`.
   - Acción del botón (ambos casos): `Executions.generateInsight(executionId)` (o el grupo elegido en el punto 1) con estado `loading` local; en éxito llama `onRegenerated?.()`; en error HTTP 404 con `local_insights_disabled` muestra el texto literal `Activá "Insights locales de ejecuciones" en Configuración → Arnés`; otros errores muestran el mensaje del error.
   - Estilos en `ExecutionInsightBlock.module.css` usando tokens de `theme.css` existentes (sin hex hardcodeado — gotcha dark theme del repo).

3. `ExecutionDetailDrawer.tsx`: donde el drawer renderiza las secciones de la ejecución cargada (`execQ.data`), agregar el bloque:
   ```tsx
   <ExecutionInsightBlock
     executionId={executionId!}
     insight={(execQ.data as any)?.metadata?.local_insight ?? null}
     onRegenerated={() => execQ.refetch()}
   />
   ```
   (el payload de `Executions.byId` incluye `metadata` — `models.py:290`; si el tipo del detalle no declara `metadata`, extenderlo con `metadata?: Record<string, unknown>`).

4. `ExecutionHistoryPage.tsx`: en la celda donde hoy se muestra el título del ticket de cada fila, agregar debajo:
   ```tsx
   {it.local_insight?.tldr ? (
     <div className={styles.insightTldr} title={it.local_insight.tldr}>{it.local_insight.tldr}</div>
   ) : null}
   ```
   y en `ExecutionHistoryPage.module.css` la clase `.insightTldr` (font-size menor, color secundario del theme, `max-width` + `overflow: hidden; text-overflow: ellipsis; white-space: nowrap`).

**Tests (TDD), `frontend/src/components/__tests__/ExecutionInsightBlock.test.tsx`** (vitest + testing-library, patrón de los tests existentes en ese directorio; mockear el módulo `endpoints` con `vi.mock`):
- `renders tldr labels and risk when insight done`.
- `renders triage rows when failure fields present`.
- `renders generate button when insight missing` + `click calls generateInsight` (mock resuelto → `onRegenerated` llamado).
- `shows flag hint on local_insights_disabled error` (mock rechaza con error cuyo mensaje contiene `local_insights_disabled` → aparece el texto `Configuración → Arnés`).

**Comandos:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/components/__tests__/ExecutionInsightBlock.test.tsx
npx tsc --noEmit
```
**Criterio:** vitest verde y `tsc` con 0 errores nuevos (comparar contra HEAD si el checkout arrastra errores preexistentes).
**Flag protectora:** la UI es inerte sin datos: con flag OFF el backend manda `local_insight: null` → solo aparece el botón opcional, cuyo click devuelve el hint de activación. Sin fetches extra de flags.
**Impacto por runtime:** N/A (presentación).
**Trabajo del operador:** ninguno.

---### F5 — Digest narrado (opt-in por click en la card existente)

**Objetivo:** narrar el digest determinista existente en 5-8 líneas de castellano con el modelo local, a un click, en la `WeeklyDigestCard` que ya existe.

**Archivos a editar:**
- `Stacky Agents/backend/services/local_insights.py` (agregar `narrate_digest`)
- `Stacky Agents/backend/api/reports.py`
- `Stacky Agents/frontend/src/api/endpoints.ts` (param opcional del wrapper del digest)
- `Stacky Agents/frontend/src/components/WeeklyDigestCard.tsx`
- `Stacky Agents/frontend/src/components/__tests__/WeeklyDigestCard.test.tsx` (extender el existente)

**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan117_digest_narrative.py`

**Cambios exactos:**

1. `services/local_insights.py`:

```python
def narrate_digest(digest: dict) -> str:
    """Narra el digest (compose_digest, services/run_digest.py:10) con el modelo local.

    Devuelve texto plano (cap NARRATIVE_MAX). Lanza la excepción del bridge si falla:
    el caller (api/reports.py) decide cómo degradar.
    """
    from copilot_bridge import invoke_local_llm  # import lazy

    system, user = build_digest_narrative_prompt(digest)
    resp = invoke_local_llm(
        agent_type="local_insights",
        system=system,
        user=user,
        on_log=lambda level, msg: None,
        execution_id=None,
    )
    return (resp.text or "").strip()[:NARRATIVE_MAX]
```
   NOTA de verificación previa: confirmar en `copilot_bridge.py:190` que `invoke_local_llm` acepta `execution_id=None` (lo acepta si el parámetro solo se usa para logging/metadata; si exigiera int, pasar `execution_id=0` y documentarlo en el código).

2. `api/reports.py`, dentro de `get_digest()` (`reports.py:12-20`), después de `digest = compose_digest(days=days, project=project)` y ANTES del branch `fmt == "json"`:

```python
    # Plan 117 — narrativa local opt-in. Sin ?narrate=1 el payload es byte-idéntico al actual.
    if request.args.get("narrate") == "1":
        import config as _config
        from services.local_insights import narrate_digest

        cfg = _config.config
        enabled = (
            getattr(cfg, "STACKY_LOCAL_INSIGHTS_ENABLED", False)
            and getattr(cfg, "STACKY_LOCAL_INSIGHTS_DIGEST_NARRATIVE_ENABLED", False)
            and getattr(cfg, "LOCAL_LLM_ENABLED", False)
            and bool(getattr(cfg, "LOCAL_LLM_ENDPOINT", ""))
        )
        if not enabled:
            digest["narrative"] = None
            digest["narrative_error"] = "narrative_disabled"
        else:
            try:
                digest["narrative"] = narrate_digest(digest)
                digest["narrative_error"] = None
            except Exception as e:  # noqa: BLE001 — el digest NUNCA falla por la narrativa
                digest["narrative"] = None
                digest["narrative_error"] = str(e)[:200]
```
   (aplica a los 3 `fmt`; `to_markdown`/`to_html` ignoran keys desconocidas — verificar; si alguno itera keys, agregar la narrativa solo en el branch `fmt == "json"` y documentarlo).

3. `endpoints.ts`: el wrapper existente del digest (buscar `digest` en el archivo — lo consume `WeeklyDigestCard.tsx`) gana un parámetro opcional `narrate?: boolean` que agrega `&narrate=1` al query string. Tipo del payload: `narrative?: string | null; narrative_error?: string | null;` (aditivo).

4. `WeeklyDigestCard.tsx`: agregar un botón `Narrar (IA local)` que hace refetch del digest con `narrate: true` y muestra: spinner mientras carga (el modelo local puede tardar; reutilizar el patrón de loading de la card), el párrafo `narrative` en un `<p>` cuando llega, o un texto suave cuando `narrative_error`: si es `narrative_disabled` → `Activá "Narrativa local del digest" en Configuración → Arnés`; si no → `El modelo local no respondió: <narrative_error>`. El botón NO se dispara solo (opt-in por click; la card jamás bloquea su render inicial esperando al LLM).

**Tests (TDD), `tests/test_plan117_digest_narrative.py`** (client Flask; mock `copilot_bridge.invoke_local_llm` en módulo origen):
- `test_digest_without_narrate_param_unchanged`: sin `?narrate=1` el JSON NO contiene las keys `narrative`/`narrative_error` (byte-compat) y el mock no se llamó.
- `test_digest_narrate_flags_off_returns_disabled`: `?narrate=1` con flags OFF → 200, `narrative=None`, `narrative_error="narrative_disabled"`, mock no llamado.
- `test_digest_narrate_ok`: flags ON (las 2 del plan + `LOCAL_LLM_ENABLED` + endpoint) + mock devuelve texto → `narrative` presente y recortada a ≤1200 chars, `narrative_error=None`, y el resto del digest (keys `totals`, `by_agent_type`, ...) intacto.
- `test_digest_narrate_model_failure_degrades`: mock lanza → 200 con `narrative=None`, `narrative_error` no vacío, digest base intacto.

**Vitest (extender `WeeklyDigestCard.test.tsx`):**
- `narrate button renders and shows narrative after click` (fetch/wrapper mockeado con `narrative: "..."`).
- `narrate disabled shows harness hint` (`narrative_error: "narrative_disabled"` → texto `Configuración → Arnés`).

**Comandos:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests\test_plan117_digest_narrative.py -q
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/components/__tests__/WeeklyDigestCard.test.tsx
```
**Criterio:** ambos verdes.
**Flag protectora:** `STACKY_LOCAL_INSIGHTS_DIGEST_NARRATIVE_ENABLED` (hija, default OFF) + master + gates LOCAL_LLM.
**Impacto por runtime:** N/A (opera sobre el digest agregado, que ya consolida los 3 runtimes vía metadata `runtime`).
**Trabajo del operador:** opt-in por click (cero pasos obligatorios).

---

### F6 — Ratchet, no-regresión e integración final

**Objetivo:** registrar los tests nuevos en el ratchet, verificar cero regresiones en las superficies tocadas y cerrar criterios binarios globales.

**Archivos a editar:**
- `Stacky Agents/backend/scripts/run_harness_tests.sh` (lista `HARNESS_TEST_FILES`)
- `Stacky Agents/backend/scripts/run_harness_tests.ps1` (lista espejo)

**Cambios exactos:** agregar a AMBAS listas (mismo formato que las entradas `test_plan106_*` ya presentes en cada script):
```
tests/test_plan117_insights_flags.py
tests/test_plan117_insights_core.py
tests/test_plan117_insights_sweep.py
tests/test_plan117_insights_api.py
tests/test_plan117_digest_narrative.py
```

**Verificación integral (correr TODO, leer el output real — cero falsos verdes):**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.\.venv\Scripts\python.exe -m pytest tests\test_plan117_insights_flags.py tests\test_plan117_insights_core.py tests\test_plan117_insights_sweep.py tests\test_plan117_insights_api.py tests\test_plan117_digest_narrative.py -q
# No-regresión de las superficies tocadas:
.\.venv\Scripts\python.exe -m pytest tests\test_harness_flags.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_harness_flags_requires.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_plan106_local_llm_bridge.py tests\test_plan106_analyze_code_api.py tests\test_plan106_playground_api.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_plan39_history.py -q   # si el archivo del plan 39 tiene otro nombre, correr el/los tests que cubren /executions/history (localizar con: grep -l "executions/history" tests/)
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx tsc --noEmit
npx vitest run src/components/__tests__/ExecutionInsightBlock.test.tsx src/components/__tests__/WeeklyDigestCard.test.tsx
```

**Criterios de aceptación (binarios, TODOS):**
1. Los 5 archivos de test del plan: verdes.
2. `test_harness_flags.py` y `test_harness_flags_requires.py`: cero fallas NUEVAS vs. HEAD (el drift conocido de `harness_defaults.env` no cuenta como regresión del plan; documentar en el reporte cualquier fail preexistente re-demostrado en HEAD).
3. Tests del plan 106 y del historial (plan 39): verdes (o idénticos a HEAD).
4. `tsc --noEmit`: 0 errores nuevos.
5. Vitest de los 2 archivos frontend: verdes.
6. Grep del diff: cero referencias nuevas a `invoke_copilot`/`_invoke_copilot` (costo cloud cero).
7. `run_harness_tests.sh` y `.ps1` contienen las 5 entradas nuevas (el meta-test del ratchet lo exige).

**Flag / runtime / operador:** N/A (fase de verificación).

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Mitigación (en el diseño) |
|---|---|---|
| R1 | El modelo local chico devuelve JSON inválido o vacío | `parse_insight_response` defensivo (fences, caps, ValueError controlado) → `state="failed"` visible con botón Reintentar; el sweep NO reintenta solo (§4.2). |
| R2 | Carga de CPU/GPU de la máquina del operador | Topes duros: `MAX_PER_CYCLE` (default 3), `SWEEP_SEC` (default 180, mín 30), `LOOKBACK_DAYS` (default 7); un solo thread; `LOCAL_LLM_TIMEOUT_SEC` ya capa cada llamada (harness_flags.py:2431-2432). |
| R3 | Recursión (el sweep anota ejecuciones que el propio LLM local genera) | Triple exclusión (`EXCLUDED_AGENT_TYPES`, prefijo `local_llm_`, `metadata.backend=="local_llm"`) + el insight NO crea filas `AgentExecution`. |
| R4 | Race sweep vs. regeneración manual sobre la misma fila | Sweep single-thread; last-write-wins declarado aceptable (mono-operador; el insight es anotación derivada, no dato fuente). |
| R5 | Locks de DB retenidos durante inferencias de minutos | La llamada LLM ocurre FUERA de `session_scope` (dos scopes cortos: leer view / escribir insight). |
| R6 | Filas con `metadata_json` NULL invisibles para el sweep | `or_(is_(None), ~contains(...))` explícito en `pick_candidates` + test de regresión dedicado. |
| R7 | Crecimiento del payload de `/history` | Insight capado a ~1.5 KB por los límites del contrato §4. |
| R8 | La card del digest se bloquea esperando al LLM | La narrativa es SOLO por click (nunca en el render inicial) y el digest degrada con `narrative_error` sin romper el payload. |
| R9 | Privacidad | Es el punto fuerte: logs/output jamás salen de la máquina (todo por `invoke_local_llm` → endpoint local). |

## 7. Fuera de scope (explícito)

- Clasificación/etiquetado de tickets o work items (otro dominio).
- Notificaciones push/webhooks nuevos (el digest ya tiene su webhook `digest.ready`, app.py:381 — no se toca).
- Resumen en streaming de runs EN VIVO (solo post-mortem de filas terminadas).
- Narrativa automática del digest sin click, y reintentos automáticos de insights `failed` (ambos romperían el presupuesto de fondo; HITL manda).
- Backfill histórico masivo más allá de `LOOKBACK_DAYS`.
- Cambios en `ActiveRunsPanel.tsx` o `frontend/src/components/devops/*` (WIP ajeno vivo; superficie prohibida para este plan).
- Embeddings/vectores (los planes 112/115 son dueños del retrieval).
- Cualquier uso de modelos cloud (Claude/Copilot) — este plan es 100% local.

## 8. Glosario (para modelos menores)

- **AgentExecution**: fila de la tabla de ejecuciones (`backend/models.py`); todo run de agente de cualquier runtime persiste ahí. `metadata_dict` es la propiedad que (de)serializa la columna Text `metadata_json` (models.py:219, 260-265).
- **Runtime vs LLM_BACKEND**: runtime = quién ejecutó el run (claude_code_cli / codex_cli / github_copilot, vive en metadata); LLM_BACKEND = backend de chat del editor. Este plan no toca ninguno de los dos: consume `invoke_local_llm`, que ignora LLM_BACKEND (copilot_bridge.py:7, 190).
- **Modelo local / Ollama**: servidor OpenAI-compatible en la máquina del operador (`LOCAL_LLM_ENDPOINT`, ej. `http://localhost:11434/v1/chat/completions`), modelo `LOCAL_LLM_MODEL` (ej. `qwen3:32b`). Costo por token: cero.
- **Arnés / FlagSpec / registry**: sistema de flags configurable por UI (`services/harness_flags.py` + `HarnessFlagsPanel`). Gotchas duros: sin `default=` en FlagSpec nuevas; default efectivo en `config.py`; `requires` profundidad 1 + `_REQUIRES_MAP_FROZEN`.
- **Sweep / daemon**: thread de fondo con loop try/except + sleep (patrón `app.py:394-409`).
- **Ratchet**: los scripts `run_harness_tests.sh/.ps1` listan TODOS los archivos de test del arnés; un meta-test (plan 49) falla si un test nuevo no está registrado.
- **Fences**: bloque markdown ```...``` que los modelos suelen envolver alrededor del JSON; hay que quitarlo antes de `json.loads` (patrón `api/local_llm_analysis.py:324-327`).
- **HITL**: human-in-the-loop — el sistema sugiere, el operador decide; prohibido ejecutar acciones mutantes.
- **TL;DR / triage**: resumen ultracorto / diagnóstico de falla (causa probable + evidencia + siguiente paso).
- **Drift de harness_defaults.env**: desajuste conocido y preexistente entre el env del deploy y el registry que hace fallar algunos tests centinela; NO es responsabilidad de este plan (solo exige "cero fallas nuevas").

## 9. Orden de implementación

1. **F0** — flags + config + help + mapa requires (`test_plan117_insights_flags.py` verde).
2. **F1** — núcleo puro (`test_plan117_insights_core.py` verde).
3. **F2** — persistencia + sweep + daemon (`test_plan117_insights_sweep.py` verde).
4. **F3** — API historial + endpoint generate (`test_plan117_insights_api.py` verde).
5. **F4** — UI historial + drawer (`ExecutionInsightBlock.test.tsx` + `tsc` verdes).
6. **F5** — digest narrado backend + card (`test_plan117_digest_narrative.py` + `WeeklyDigestCard.test.tsx` verdes).
7. **F6** — ratchet + verificación integral (criterios 1-7).

Cada fase es autocontenida: se puede mergear F0-F3 sin F4/F5 (el insight ya viaja en los payloads) y F5 es independiente de F4.

## 10. Definición de Hecho (DoD) global

- [ ] Las 5 flags existen, categorizadas, con bounds, default efectivo OFF en `config.py`, hijas con `requires` al master, aristas en `_REQUIRES_MAP_FROZEN`, y ayuda en `harness_flags_help.py`.
- [ ] `services/local_insights.py` implementa el contrato §4 completo (elegibilidad, prompts, parseo, persistencia, sweep, narrativa) con la llamada LLM fuera de `session_scope`.
- [ ] El daemon `stacky-local-insights-daemon` arranca siempre y sus gates son hot (flag ON/OFF sin restart).
- [ ] `GET /api/executions/history` incluye `local_insight` (aditivo, null-safe); `POST /api/llm/insights/<id>/generate` cumple la matriz 200/404/409/502.
- [ ] UI: TL;DR en fila del historial, bloque completo en el drawer con botón generar/reintentar, narrativa del digest a un click en la card existente; cero cambios en `ActiveRunsPanel.tsx` y `devops/*`.
- [ ] Los 5 archivos de test backend + 2 frontend nombrados en este doc: verdes con los comandos literales (venv `backend\.venv`, vitest por archivo).
- [ ] `run_harness_tests.sh` y `.ps1` registran los 5 tests backend.
- [ ] Con la flag master OFF: payloads byte-compatibles (campo aditivo null/ausente) y cero llamadas al modelo local (verificado por tests con mock).
- [ ] Cero referencias nuevas a modelos cloud en el diff (KPI costo cero).
- [ ] Encabezado de estado de este doc actualizado por cada eslabón del pipeline (feedback del operador: mantener sincronizado PROPUESTO → CRITICADO → IMPLEMENTADO).
