# Plan 264 — Herramienta, modelo y effort elegibles en TODO punto de uso: una sola matriz de capacidades, una sola resolución, un solo selector

**Estado:** PROPUESTO v1 (2026-07-27) · **Autor:** pipeline `proponer-plan-stacky` · **Juez:** pendiente (`criticar-y-mejorar-plan`)

---

## 1. Objetivo y KPI

Stacky ya tiene las tres piezas buenas: el catálogo vivo por runtime
(`services/model_catalog.py`, Plan 159 + 212), la matriz de clamp
(`services/llm_router.py::clamp_model` / `::clamp_effort_for_model`, Plan 212 F2) y un selector reusable
bien diseñado (`components/ModelEffortPicker.tsx`, Plan 212 F4). Lo que falta es **cobertura y unicidad**:

1. **El effort NO llega a Codex.** `agent_runner.py:256-264` invoca `start_codex_cli_run(...)` pasando
   `model_override` pero **sin** `effort_override` — y `start_codex_cli_run` ni siquiera acepta ese
   parámetro (`services/codex_cli_runner.py:87-96`). Es exactamente el mismo falso verde que el Plan 196
   descubrió y arregló para `claude_code_cli` (`agent_runner.py:344-350`): **el gemelo de Codex sigue
   vivo**. El operador elige "high" y Codex corre como si no hubiera elegido nada.
2. **La lista de efforts está escrita 4 veces.** `api/agents.py:425` (`_VALID_EFFORTS`),
   `api/devops_agent.py:15` (`_EFFORTS`), `api/devops_remote_console.py:212` y `:313` (literal inline
   duplicado), `services/claude_code_cli_runner.py:2224` (`CLI_VALID_EFFORTS`). Agregar un effort nuevo
   hoy exige tocar 5 lugares y ninguno falla si te olvidás de uno.
3. **10 de 17 puntos de lanzamiento no ofrecen elección.** `run_agent(...)` se llama desde 17 lugares;
   `phase6.py:192`, `phase6.py:229`, `doc_documenter.py:383`, `pipeline_orchestrator.py:58`,
   `slash_commands.py:101`, `variant_generator.py:188`, `devops_section_doctor.py:171` y las restantes
   de `parallel_runs.py` **no pasan ni modelo ni effort**: corren con lo que caiga.
4. **El selector está cableado en 2 pantallas de 4.** `ModelEffortPicker` sólo lo usan
   `EpicFromBriefModal.tsx:491` y `TicketBoard.tsx:221`. `PlansBoardPage.tsx:150-159,341` y
   `IncidentResolverModal.tsx:83-96` tienen **cada uno su propio selector hecho a mano**, con su propia
   lógica de defaults y degradación.
5. **El historial no registra qué se usó, salvo en Claude.** `build_model_effort_trace` y
   `_persist_model_effort_trace` viven sólo en `claude_code_cli_runner.py:516-561`. Una corrida de Codex
   no deja rastro del effort pedido vs. el efectivo.

| KPI | Antes (medido 2026-07-27) | Después (criterio binario) |
|---|---|---|
| **KPI-1** Literales de la lista de efforts en el backend | **5** | **1** (`services/runtime_capabilities.py`) |
| **KPI-2** Llamadas a `run_agent(...)` sin resolución de modelo/effort | **10** | **0** |
| **KPI-3** Runtimes en los que el `effort` elegido llega al runner | **1** (claude) | **3** (claude directo, codex por presupuesto de turnos, copilot declarado no-aplicable) |
| **KPI-4** Selectores de modelo/effort implementados a mano en el frontend | **2** | **0** |
| **KPI-5** Ejecuciones cuyo `metadata_dict` registra `{tool, model, effort_requested, effort_effective}` | sólo claude | **los 3 runtimes** |

---

## 2. Por qué ahora / gap que cierra

El Plan 212 (`212_PLAN_SELECTOR_VIVO_DE_MODELO_Y_EFFORT_EN_TICKETS_ADO_Y_CUMPLIMIENTO_REAL_DE_LA_ELECCION.md`)
puso el título correcto: **"cumplimiento real de la elección"**. Construyó la matriz, el picker y el
trace — pero acotado al tablero de tickets ADO. El Plan 196, al implementarse el 2026-07-26, encontró
por casualidad que la rama `claude_code_cli` de `run_agent` descartaba el effort en silencio, y lo
arregló con una línea. Este plan hace lo que faltó: **buscar el resto de los lugares donde la elección
se descarta, en vez de esperar a tropezarlos.** Y ya encontró uno idéntico en Codex.

El gap no es "falta un selector". Es que **la elección tiene 5 fuentes de verdad y 4 implementaciones**,
así que cada superficie nueva reinventa la degradación y cada una se equivoca distinto.

---

## 3. Principios y guardarraíles

1. **3 runtimes con paridad explícita, incluida la degradación honesta.** El effort **no existe** como
   flag de línea de comandos en Codex: `codex_cli_runner.py:580` lo dice literalmente — *"Codex no tiene
   --effort; se ajusta el presupuesto de turnos bajo el cap"*. Y GitHub Copilot Pro no expone effort en
   absoluto. La regla de este plan: **la capacidad se declara, no se finge**. Cada runtime declara
   `effort_mode` ∈ `{"nativo", "presupuesto_turnos", "no_aplica"}`, y la UI muestra al operador qué va a
   pasar realmente con su elección. **Prohibido** mostrar un selector que no hace nada.
2. **Cero trabajo extra para el operador.** Todo tiene default: el catálogo ya trae `default_model` y
   `default_effort` por runtime. Si el operador no toca nada, se comporta como hoy o mejor. Todas las
   flags de este plan nacen **ON** — ninguna cae en las categorías de excepción (ver §5 F0).
3. **Human-in-the-loop.** La resolución **nunca** escala el effort por su cuenta por encima de lo que el
   operador pidió explícitamente. El selector adaptativo existente (`services/adaptive_selector.py`)
   sigue siendo el piso, no el techo: **un override explícito siempre gana** (es la regla que ya
   respeta `claude_code_cli_runner.py:957-961`).
4. **Mono-operador sin auth.** La preferencia se guarda por **proyecto**, no por usuario. Nada de RBAC.
5. **Backward-compatible.** `_clamp_effort_for_model` (`api/agents.py:612`) y `CLI_VALID_EFFORTS`
   (`claude_code_cli_runner.py:2224`) **se conservan como delegadores** al módulo único. No se borra
   ningún símbolo público: se vacía su implementación. Las firmas de `run_agent`,
   `start_claude_code_cli_run` y `start_codex_cli_run` sólo ganan parámetros keyword-only con default.
6. **No degradar.** El módulo nuevo es aritmética pura sobre un dict ya cacheado. Cero I/O nuevo, cero
   red, cero llamada a modelo. `load_model_catalog()` ya tiene su caché TTL 300 s
   (`model_catalog.py:16`) y no se toca.
7. **Reusar.** Catálogo del 159/212, clamp del `llm_router`, picker del 212 F4, preferencias de
   `api/preferences.py`, telemetría del 171/258. **No se crea ningún catálogo nuevo.**

---

## 4. Glosario

| Término | Significado |
|---|---|
| **runtime / herramienta** | `claude_code_cli`, `codex_cli` o `github_copilot`. Es lo que el usuario llama "herramienta o proveedor". |
| **catálogo** | `config/model_catalog.json` leído por `services/model_catalog.py`, con `models`, `efforts`, `effort_support`, `effort_degrade`, `default_model`, `default_effort` por runtime. |
| **clamp de modelo** | `llm_router.clamp_model`: mapea tiers prohibidos (opus/fable) a `CLAUDE_CAP_MODEL = "claude-sonnet-5"` salvo `allow_opus`. |
| **clamp de effort** | `llm_router.clamp_effort_for_model`: baja el effort al máximo que soporta el modelo elegido. |
| **effort_mode** | **NUEVO**: cómo un runtime materializa el effort. `nativo` (flag del CLI), `presupuesto_turnos` (se traduce a más/menos turnos) o `no_aplica`. |
| **selección resuelta** | **NUEVO**: la tupla `(runtime, model, effort_requested, effort_effective, origen)` que sale de `resolve_run_selection()`. |
| **origen** | De dónde salió cada valor: `"explicito"`, `"preferencia"`, `"adaptativo"` o `"default_catalogo"`. |
| **trace** | El dict que `build_model_effort_trace` persiste en `metadata_dict["model_effort"]` de la ejecución. |

---

## 5. Fases

### F0 — Flags (patrón triple)

**Objetivo.** Dar de alta las 4 flags del plan.

**Archivos a editar (2):**

1. `Stacky Agents/backend/config.py` — insertar en el mismo bloque donde vive
   `STACKY_MODEL_PROBE_ENABLED` (ubicalo con `grep -n "STACKY_MODEL_PROBE_ENABLED" config.py`),
   siguiendo el patrón literal de las líneas vecinas:

```python
    # Plan 264 — una sola matriz de capacidades de runtime/modelo/effort.
    STACKY_RUNTIME_CAPABILITIES_ENABLED: bool = os.getenv(
        "STACKY_RUNTIME_CAPABILITIES_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes")
    STACKY_CODEX_EFFORT_PARITY_ENABLED: bool = os.getenv(
        "STACKY_CODEX_EFFORT_PARITY_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes")
    STACKY_RUN_SELECTION_PREFS_ENABLED: bool = os.getenv(
        "STACKY_RUN_SELECTION_PREFS_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes")
    STACKY_MODEL_PICKER_EVERYWHERE_ENABLED: bool = os.getenv(
        "STACKY_MODEL_PICKER_EVERYWHERE_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes")
```

2. `Stacky Agents/backend/services/harness_flags.py` — 4 `FlagSpec` + las 4 keys en
   `_CURATED_DEFAULTS_ON` (junto a `"STACKY_MODEL_PROBE_ENABLED"`, `harness_flags.py:454`):

```python
    # ── Plan 264 — herramienta/modelo/effort elegibles en todo punto de uso ──
    FlagSpec(
        key="STACKY_RUNTIME_CAPABILITIES_ENABLED",
        type="bool", default=True,   # Curada en _CURATED_DEFAULTS_ON.
        label="Matriz unica de capacidades de runtime",
        description=(
            "Plan 264 — Una sola fuente para 'que modelos y efforts admite cada "
            "herramienta y como degrada'. Reemplaza las 5 copias de la lista de "
            "efforts. Calculo puro sobre el catalogo ya cacheado."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_CODEX_EFFORT_PARITY_ENABLED",
        type="bool", default=True,   # Curada en _CURATED_DEFAULTS_ON.
        label="El effort elegido llega tambien a Codex",
        description=(
            "Plan 264 — Codex no tiene --effort: el esfuerzo elegido se traduce a "
            "presupuesto de turnos (codex_cli_runner.py:580). Hoy se descarta en "
            "silencio (agent_runner.py:256-264). Solo aplica a corridas que el "
            "operador lanza; no enciende ningun proceso de fondo."
        ),
        group="global",
        requires="STACKY_RUNTIME_CAPABILITIES_ENABLED",
    ),
    FlagSpec(
        key="STACKY_RUN_SELECTION_PREFS_ENABLED",
        type="bool", default=True,   # Curada en _CURATED_DEFAULTS_ON.
        label="Recordar herramienta/modelo/effort por proyecto",
        description=(
            "Plan 264 — La ultima eleccion del operador se guarda en el archivo de "
            "preferencias de Stacky (api/preferences.py) y se preselecciona la "
            "proxima vez. Un override explicito siempre gana."
        ),
        group="global",
        requires="STACKY_RUNTIME_CAPABILITIES_ENABLED",
    ),
    FlagSpec(
        key="STACKY_MODEL_PICKER_EVERYWHERE_ENABLED",
        type="bool", default=True,   # Curada en _CURATED_DEFAULTS_ON.
        label="Selector de modelo/effort en todas las pantallas",
        description=(
            "Plan 264 — El mismo ModelEffortPicker (Plan 212 F4) en el tablero de "
            "planes, la bandeja de incidencias y las secciones DevOps, en vez de un "
            "selector distinto hecho a mano en cada pantalla."
        ),
        group="global",
        requires="STACKY_RUNTIME_CAPABILITIES_ENABLED",
    ),
```

**Por qué las 4 nacen ON (justificación explícita, aunque el default ON no la exija):** ninguna
enciende loops, daemons, barridos, polling ni prefetch — no hay **categoría (A)**. Ninguna escribe en
ADO/GitLab/repo remoto, ni ejecuta DDL/DML, ni despliega, ni borra datos, ni decide por el operador —
no hay **categoría (B)**. `STACKY_CODEX_EFFORT_PARITY_ENABLED` sí puede hacer que una corrida de Codex
consuma más turnos, pero **sólo dentro de una corrida que el operador lanzó explícitamente y con el
esfuerzo que él eligió**: eso es on-demand, no consumo en reposo. `STACKY_RUN_SELECTION_PREFS_ENABLED`
escribe únicamente en el archivo de preferencias del propio Stacky, que `api/preferences.py:32` ya
escribe hoy — no es un sistema del operador.

**Tests:**
```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_harness_flags.py" -q
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_harness_flags_requires.py" -q
```
**Criterio binario.** Ambos exit 0.
**Impacto por runtime:** ninguno (configuración). **Trabajo del operador: ninguno.**

---

### F1 — Backend: `services/runtime_capabilities.py`, la única matriz (TDD)

**Objetivo.** Un solo módulo que responda "¿qué admite esta herramienta y cómo degrada?", y que las 5
copias de la lista de efforts pasen a delegar en él.

**Archivo a crear:** `Stacky Agents/backend/services/runtime_capabilities.py`.

**Test PRIMERO:** `Stacky Agents/backend/tests/test_plan264_runtime_capabilities.py`.

**Contrato (símbolos exactos):**

```python
# El ÚNICO literal de efforts del backend. Todo lo demás delega acá.
EFFORTS: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")
EFFORT_ORDER: dict[str, int] = {e: i for i, e in enumerate(EFFORTS)}

RUNTIMES: tuple[str, ...] = ("claude_code_cli", "codex_cli", "github_copilot")

# Cómo materializa el effort cada runtime. Declarativo, no inferido.
EFFORT_MODE: dict[str, str] = {
    "claude_code_cli": "nativo",              # el CLI acepta el esfuerzo directo
    "codex_cli":       "presupuesto_turnos",  # codex_cli_runner.py:580 — no hay --effort
    "github_copilot":  "no_aplica",           # el bridge no expone esfuerzo
}

# Traducción de effort → turnos extra para codex_cli. Es el inverso del mapeo
# que ya existe en codex_cli_runner.py:585 ({"S":"low","M":"medium","L":"high","XL":"high"}).
CODEX_EFFORT_TURNS: dict[str, int] = {
    "low": 0, "medium": 1, "high": 2, "xhigh": 2, "max": 3,
}


def is_valid_effort(effort: str | None) -> bool:
    """True si `effort` (case-insensitive, sin espacios) está en EFFORTS."""


def capabilities_for(runtime: str) -> dict:
    """Capacidades REALES de un runtime, leyendo el catálogo vivo.

    Devuelve SIEMPRE estas claves (nunca lanza, nunca devuelve None):
      {
        "runtime": str,
        "known": bool,                 # False si `runtime` no está en RUNTIMES
        "effort_mode": str,            # "nativo" | "presupuesto_turnos" | "no_aplica"
        "supports_model": bool,        # hay >=1 modelo elegible
        "supports_effort": bool,       # effort_mode != "no_aplica"
        "models": list[dict],          # del catálogo, tal cual
        "efforts": list[str],          # EFFORTS filtrado por lo que declare el catálogo
        "default_model": str | None,
        "default_effort": str | None,
        "effort_note": str,            # frase corta para la UI, en español
      }
    `effort_note` por modo:
      nativo              -> "El esfuerzo se le pasa directo a la herramienta."
      presupuesto_turnos  -> "Codex no acepta un esfuerzo explícito: se traduce a más turnos de trabajo."
      no_aplica           -> "Esta herramienta no expone niveles de esfuerzo; el selector no se muestra."
    """


def clamp_selection(runtime: str, model: str | None, effort: str | None,
                    *, allow_opus: bool = False) -> dict:
    """Ajusta (model, effort) a lo que el runtime realmente soporta.

    Devuelve {"model": str|None, "effort": str|None,
              "effort_requested": str|None, "degraded": bool, "reason": str|None}.
    - Delega el clamp de modelo en llm_router.clamp_model(model, allow_opus)
      SOLO para claude_code_cli (los otros runtimes no usan modelos Claude).
    - Delega el clamp de effort en llm_router.clamp_effort_for_model(effort, model).
    - Si effort_mode == "no_aplica" -> effort=None, degraded=True,
      reason="github_copilot no expone niveles de esfuerzo".
    - Un effort inválido cae al default_effort del catálogo, degraded=True.
    NUNCA lanza.
    """


def codex_turn_budget(effort: str | None, base_turns: int) -> int:
    """Turnos que le corresponden a Codex para ese esfuerzo. base_turns + CODEX_EFFORT_TURNS.
    effort None o inválido -> base_turns (sin cambio). Nunca lanza, nunca devuelve < base_turns."""
```

**Casos de test (mínimo 18):**

| # | Caso | Aserción |
|---|---|---|
| 1 | `EFFORTS` | `== ("low","medium","high","xhigh","max")` |
| 2 | `is_valid_effort("HIGH ")` | `True` (normaliza) |
| 3 | `is_valid_effort("turbo")` / `None` / `""` | `False` |
| 4 | `capabilities_for("claude_code_cli")["effort_mode"]` | `"nativo"` |
| 5 | `capabilities_for("codex_cli")["effort_mode"]` | `"presupuesto_turnos"` |
| 6 | `capabilities_for("github_copilot")["supports_effort"]` | `False` |
| 7 | `capabilities_for("inventado")["known"]` | `False`, y no lanza |
| 8 | `capabilities_for(...)` con el catálogo caído (monkeypatch que hace lanzar a `load_model_catalog`) | devuelve el dict completo igual, `known` correcto |
| 9 | `clamp_selection("claude_code_cli","claude-opus-4-8","max")` | `model == "claude-sonnet-5"`, `degraded is True` |
| 10 | idem con `allow_opus=True` | `model == "claude-opus-4-8"` |
| 11 | `clamp_selection("claude_code_cli","claude-haiku-4-5","max")` | `effort == "high"` (según `effort_degrade` del catálogo), `degraded is True` |
| 12 | `clamp_selection("github_copilot", None, "high")` | `effort is None`, `degraded is True`, `reason` no vacío |
| 13 | `clamp_selection("codex_cli", None, "high")` | `effort == "high"` (se conserva; lo materializa el presupuesto) |
| 14 | `clamp_selection("claude_code_cli", None, "turbo")` | `effort == default_effort` del catálogo, `degraded is True` |
| 15 | `clamp_selection(...)["effort_requested"]` | siempre trae lo pedido original, aunque haya degradado |
| 16 | `codex_turn_budget("max", 10)` | `13` |
| 17 | `codex_turn_budget(None, 10)` / `codex_turn_budget("turbo", 10)` | `10` |
| 18 | flag OFF (`config.config.STACKY_RUNTIME_CAPABILITIES_ENABLED = False`) | `clamp_selection` devuelve `(model, effort)` sin tocar y `degraded is False` |

> **Gotcha obligatorio:** leé la flag por **`config.config.STACKY_...`** (la instancia), nunca
> `config.STACKY_...` (el módulo) — el módulo devuelve el default y el test 18 queda en falso verde.

**Deduplicación (KPI-1) — editar 5 archivos, todos por delegación, sin borrar símbolos:**

```diff
# api/agents.py:425
-    _VALID_EFFORTS = ("low", "medium", "high", "xhigh", "max")
+    from services.runtime_capabilities import EFFORTS as _VALID_EFFORTS
```
```diff
# api/devops_agent.py:15
-_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
+from services.runtime_capabilities import EFFORTS as _EFFORTS_TUPLE
+_EFFORTS = set(_EFFORTS_TUPLE)
```
```diff
# api/devops_remote_console.py:212 y :313 (las DOS ocurrencias)
-    effort_override = effort.strip().lower() if effort and effort.strip().lower() in {
-        ... literal ...
-    } else None
+    from services.runtime_capabilities import is_valid_effort
+    _e = (effort or "").strip().lower()
+    effort_override = _e if is_valid_effort(_e) else None
```
```diff
# services/claude_code_cli_runner.py:2224
-CLI_VALID_EFFORTS = ("low", "medium", "high", "xhigh", "max")
+from services.runtime_capabilities import EFFORTS as CLI_VALID_EFFORTS  # Plan 264 — símbolo conservado
```

> **Cuidado con los ciclos de import.** `runtime_capabilities` importa `model_catalog` y `llm_router`,
> y **nada más de `services/`**. `claude_code_cli_runner` ya importa de `services/`, así que el import
> a nivel de módulo es seguro; si `python -c "import services.claude_code_cli_runner"` falla por ciclo,
> movelo adentro de la función que lo usa. Verificalo con:
> ```powershell
> "Stacky Agents\backend\.venv\Scripts\python.exe" -c "import sys; sys.path.insert(0,'Stacky Agents/backend'); import services.claude_code_cli_runner, api.agents, api.devops_agent, api.devops_remote_console; print('ok')"
> ```

**Registrar** `tests/test_plan264_runtime_capabilities.py` en **ambas** listas `HARNESS_TEST_FILES`
(`backend/scripts/run_harness_tests.sh:20` y el `.ps1`), o `test_harness_ratchet_meta.py` sale rojo.

**Comando de test:**
```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_plan264_runtime_capabilities.py" -q
```

**Criterio binario.** 18 passed. Y el grep de KPI-1:
```bash
grep -rnE '\("low", *"medium", *"high", *"xhigh", *"max"\)|\{"low", *"medium", *"high", *"xhigh", *"max"\}' --include=*.py "Stacky Agents/backend" | grep -v "services/runtime_capabilities.py" | grep -v "/tests/" | wc -l
```
debe dar **0**.

**Flag:** `STACKY_RUNTIME_CAPABILITIES_ENABLED`, default **ON**.
**Impacto por runtime:** el módulo **describe** los 3; no ejecuta ninguno.
**Trabajo del operador: ninguno.**

---

### F2 — Backend: paridad real de Codex (el bug gemelo del Plan 196)

**Objetivo.** Que el effort elegido llegue a Codex, y que quede registrado.

**Archivos a editar (2):**

1. `Stacky Agents/backend/services/codex_cli_runner.py` — agregar el parámetro a
   `start_codex_cli_run` (`codex_cli_runner.py:87-96`):

```diff
 def start_codex_cli_run(
     *,
     ticket_id: int,
     ...
     model_override: str | None = None,
+    effort_override: str | None = None,
 ) -> int:
```
y en el `metadata_dict` (`codex_cli_runner.py:110-115`):
```diff
         exec_row.metadata_dict = {
             "runtime": RUNTIME,
             "vscode_agent_filename": vscode_agent_filename,
             "workspace_root": workspace_root,
             "model_override": model_override,
+            "effort_override": effort_override,   # Plan 264 — paridad con claude
         }
```
Y donde hoy se calcula `_mapped_effort_codex` (`codex_cli_runner.py:580-595`), el override explícito
debe **ganarle** al adaptativo, exactamente como ya hace Claude en `claude_code_cli_runner.py:957-961`:

```diff
-            _mapped_effort_codex = {"S": "low", "M": "medium", "L": "high", "XL": "high"}.get(
-                ..., "medium")
+            _adaptive_codex = {"S": "low", "M": "medium", "L": "high", "XL": "high"}.get(
+                ..., "medium")
+            # Plan 264 — el override explícito del operador tiene prioridad sobre el
+            # adaptativo (misma regla que claude_code_cli_runner.py:957-961).
+            from services.runtime_capabilities import is_valid_effort, codex_turn_budget
+            _mapped_effort_codex = (
+                effort_override if is_valid_effort(effort_override) else _adaptive_codex
+            )
```
y aplicar `codex_turn_budget(_mapped_effort_codex, <turnos base actuales>)` donde hoy se decide el
presupuesto de turnos. **Leé el código real de esa zona antes de editar**: el nombre de la variable de
turnos base la fija el archivo, no este documento. Si el flag
`STACKY_CODEX_EFFORT_PARITY_ENABLED` está OFF, mantené `_mapped_effort_codex = _adaptive_codex`
(comportamiento byte-idéntico al de hoy).

2. `Stacky Agents/backend/agent_runner.py:256-264` — **la línea que falta** (el gemelo exacto del fix
   del Plan 196 en `agent_runner.py:350`):

```diff
             _new_exec_id = start_codex_cli_run(
                 ticket_id=ticket_id,
                 ...
                 model_override=model_override,
+                # Plan 264 — BUG GEMELO del que el Plan 196 arregló para claude_code_cli
+                # (agent_runner.py:344-350): esta rama descartaba el effort en silencio,
+                # así que el selector era decorativo en TODA corrida codex_cli.
+                effort_override=effort_override,
             )
```

**Test PRIMERO:** `Stacky Agents/backend/tests/test_plan264_codex_effort_parity.py`:

| # | Caso | Aserción |
|---|---|---|
| 1 | `inspect.signature(start_codex_cli_run).parameters` | contiene `"effort_override"` |
| 2 | Monkeypatch de `start_codex_cli_run`; `run_agent(runtime="codex_cli", effort_override="high", ...)` | el mock fue llamado con `effort_override == "high"` |
| 3 | idem sin `effort_override` | el mock fue llamado con `effort_override is None` (no rompe llamadores viejos) |
| 4 | `start_codex_cli_run(..., effort_override="max")` con subprocess mockeado | `exec_row.metadata_dict["effort_override"] == "max"` |
| 5 | `codex_turn_budget` aplicado: effort `"max"` vs `"low"` | el presupuesto de turnos del segundo es **estrictamente menor** |
| 6 | Flag `STACKY_CODEX_EFFORT_PARITY_ENABLED = False` | el presupuesto de turnos es el mismo que sin override (comportamiento pre-261) |
| 7 | Regresión Plan 196: `run_agent(runtime="claude_code_cli", effort_override="high")` | `start_claude_code_cli_run` sigue recibiendo `effort_override="high"` |

> **Gotcha del repo (SQLITE_LOCKED):** los tests 4 y 7 tocan la DB ⇒ son **flaky bajo el shared-cache
> de pytest**. Corré este archivo **solo**, 8-12 veces seguidas, y usá el helper `run_with_retry` si el
> repo ya lo expone (`grep -rn "run_with_retry" "Stacky Agents/backend/tests" | head -3`). Un solo
> verde no alcanza para dar por buena esta fase.

**Comando de test:**
```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_plan264_codex_effort_parity.py" -q
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_runtime_dispatch.py" -q
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_runtime_metadata_roundtrip.py" -q
```
(registrar el archivo nuevo en las dos `HARNESS_TEST_FILES`).

**Criterio binario.** 7 passed × 10 corridas consecutivas sin un solo rojo, y los dos tests de
regresión de runtime en verde.

**Flag:** `STACKY_CODEX_EFFORT_PARITY_ENABLED`, default **ON** (no cae en (A) ni (B): sólo afecta
corridas que el operador lanza).
**Impacto por runtime:** Claude sin cambios (ya andaba) · Codex ahora **honra** el effort vía
presupuesto de turnos · Copilot no aplica y lo declara.
**Trabajo del operador: ninguno.**

---

### F3 — Backend: `resolve_run_selection()`, una sola cascada de precedencia

**Objetivo.** Que los 10 call sites que hoy no eligen nada pasen a resolver herramienta/modelo/effort
por la misma cascada, sin duplicar lógica.

**Archivo a editar:** `Stacky Agents/backend/services/runtime_capabilities.py` (misma casa que F1).

**Contrato:**

```python
def resolve_run_selection(
    *,
    runtime: str,
    model: str | None = None,          # explícito de la request
    effort: str | None = None,         # explícito de la request
    project_name: str | None = None,   # para leer la preferencia guardada (F4)
    adaptive_effort: str | None = None,# piso propuesto por adaptive_selector
    allow_opus: bool = False,
) -> dict:
    """Resuelve la selección final con esta precedencia EXACTA (de mayor a menor):

      1. `model` / `effort` explícitos de la request        -> origen "explicito"
      2. preferencia guardada del proyecto (si la flag ON)  -> origen "preferencia"
      3. `adaptive_effort` (sólo para effort; es PISO, no techo) -> origen "adaptativo"
      4. default_model / default_effort del catálogo        -> origen "default_catalogo"

    Después aplica clamp_selection() sobre el resultado.

    Devuelve:
      {"runtime": str, "model": str|None, "effort": str|None,
       "effort_requested": str|None, "degraded": bool, "reason": str|None,
       "origen_model": str, "origen_effort": str}
    NUNCA lanza: ante cualquier problema cae al paso 4.
    """
```

> **Regla 3 explicada (importante, no la inviertas):** `adaptive_effort` es un **piso**. Si el
> adaptativo propone `high` y el operador no eligió nada, se usa `high`. Si el operador eligió `low`
> explícitamente, gana `low` — el sistema **no** escala por su cuenta por encima de la decisión humana.
> Es la misma regla que ya respeta `claude_code_cli_runner.py:957-961`.

**Cableado de los 10 call sites.** En cada uno, reemplazar la llamada desnuda por la resuelta. Patrón
literal a aplicar (ejemplo con `services/pipeline_orchestrator.py:58`):

```diff
+    from services.runtime_capabilities import resolve_run_selection
+    _sel = resolve_run_selection(runtime=runtime, project_name=project_name)
     execution_id = agent_runner.run_agent(
         ...
+        model_override=_sel["model"],
+        effort_override=_sel["effort"],
     )
```

**Los 10 archivos:línea a editar (lista cerrada, verificada 2026-07-27):**

| # | Archivo | Línea | Nota |
|---|---|---|---|
| 1 | `Stacky Agents/backend/api/phase6.py` | 192 | |
| 2 | `Stacky Agents/backend/api/phase6.py` | 229 | |
| 3 | `Stacky Agents/backend/api/devops_section_doctor.py` | 171 | |
| 4 | `Stacky Agents/backend/services/doc_documenter.py` | 383 | |
| 5 | `Stacky Agents/backend/services/pipeline_orchestrator.py` | 58 | |
| 6 | `Stacky Agents/backend/services/slash_commands.py` | 101 | |
| 7 | `Stacky Agents/backend/services/variant_generator.py` | 188 | **OJO:** es el optimizador del Plan 169 (`_OPTIMIZER_ADO_ID = -9`). Si el archivo tiene cambios sin commitear de otra sesión, **no lo toques** y dejá el ítem pendiente registrado en el cierre. |
| 8 | `Stacky Agents/backend/services/parallel_runs.py` | 126 | |
| 9 | `Stacky Agents/backend/services/parallel_runs.py` | 169 | |
| 10 | `Stacky Agents/backend/services/macros.py` | 177 | ya pasa **uno** de los dos; completar el que falte |

> **Antes de editar cada uno, corré `git status --porcelain <archivo>`.** Este repo tiene sesiones
> paralelas: si el archivo aparece modificado y el cambio no es tuyo, **saltealo** y anotalo. Nunca
> `git stash`, `git reset` ni `git checkout --` sobre trabajo ajeno.

**Test PRIMERO:** `Stacky Agents/backend/tests/test_plan264_run_selection.py`:

| # | Caso | Aserción |
|---|---|---|
| 1 | explícito gana a preferencia | `origen_model == "explicito"` |
| 2 | preferencia gana a adaptativo | `origen_effort == "preferencia"` |
| 3 | adaptativo gana a default | `origen_effort == "adaptativo"` |
| 4 | sin nada | `origen_effort == "default_catalogo"` y `effort == default_effort` |
| 5 | explícito `"low"` + adaptativo `"high"` | `effort == "low"` (el humano no se sobreescribe) |
| 6 | runtime `github_copilot` | `effort is None`, `degraded is True` |
| 7 | runtime desconocido | no lanza; cae a defaults |
| 8 | flag prefs OFF | el paso 2 se saltea; `origen_effort` nunca es `"preferencia"` |
| 9 | Cobertura (KPI-2): AST sobre los 17 call sites | **cada** llamada a `run_agent(` pasa `model_override=` y `effort_override=` |

> **Test 9 — cómo hacerlo bien:** usá el módulo `ast` de Python, **no** un regex. La memoria del repo
> registra que un centinela textual sobre flags rompió el motor entero: exigir texto en masa es
> destructivo. Parseá cada archivo, encontrá los `ast.Call` cuyo `func` termine en `run_agent`, y
> verificá los `keywords`. Excluí `backend/evals/` (ahí `run_agent` es otra función,
> `evals/golden_runner.py:109`) y `backend/tests/`.

**Comando de test:**
```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_plan264_run_selection.py" -q
```
(registrar en las dos `HARNESS_TEST_FILES`).

**Criterio binario.** 9 passed. El test 9 **es** el KPI-2 y no admite allowlist salvo el ítem 7
(`variant_generator.py`) si quedó bloqueado por trabajo ajeno — en ese caso el test lo declara en una
allowlist de **una** entrada, con el motivo escrito.

**Flag:** `STACKY_RUNTIME_CAPABILITIES_ENABLED` (ON) y `STACKY_RUN_SELECTION_PREFS_ENABLED` (ON) para
el paso 2.
**Impacto por runtime:** la cascada es igual en los 3; lo que cambia es el clamp de F1.
**Trabajo del operador: ninguno** (todo tiene default).

---

### F4 — Backend: persistencia por proyecto + historial en los 3 runtimes

**Objetivo.** Recordar la elección y dejar rastro de qué se usó de verdad.

**(a) Persistencia.** Reusar `api/preferences.py`, que ya tiene `GET/PUT /api/preferences/ui/<key>`
(`preferences.py:74-89`). **No crear endpoints nuevos.** Clave a usar:
`runSelection.<project_name>` con el valor `{"runtime": str, "model": str|null, "effort": str|null}`.

En `runtime_capabilities.py` agregar:

```python
_PREF_KEY_PREFIX = "runSelection."

def load_run_preference(project_name: str | None) -> dict | None:
    """Lee la preferencia guardada del proyecto. None si no hay, si la flag está OFF,
    o ante CUALQUIER error. Nunca lanza."""

def save_run_preference(project_name: str | None, sel: dict) -> bool:
    """Guarda {"runtime","model","effort"} validado con is_valid_effort/clamp_selection.
    Devuelve False (sin lanzar) si la flag está OFF o el guardado falla."""
```

**(b) Historial.** Mover `build_model_effort_trace` (hoy en `claude_code_cli_runner.py:516-541`) a
`runtime_capabilities.py` **conservando el símbolo original como delegador** (hay callers por nombre), y
llamar a `_persist_model_effort_trace` también desde `codex_cli_runner`. El trace debe incluir la
herramienta:

```diff
     return {
+        "tool": runtime,                       # Plan 264 — qué herramienta corrió
         "requested_model": requested_model or "",
         "effective_model": effective_model or "",
         "requested_effort": requested_effort or "",
         "effective_effort": effective_effort or "",
+        "effort_mode": EFFORT_MODE.get(runtime, "no_aplica"),
+        "origen_model": origen_model,
+        "origen_effort": origen_effort,
     }
```

> **Leé la firma real de `build_model_effort_trace` (`claude_code_cli_runner.py:516-522`) antes de
> tocarla** y agregá los parámetros nuevos como **keyword-only con default**, para no romper a sus
> llamadores actuales.

**Test PRIMERO:** `Stacky Agents/backend/tests/test_plan264_selection_history.py`:

| # | Caso | Aserción |
|---|---|---|
| 1 | `save_run_preference` + `load_run_preference` round-trip | devuelve lo guardado |
| 2 | `load_run_preference("proyecto_inexistente")` | `None`, no lanza |
| 3 | `save_run_preference` con effort inválido | se guarda **clampeado**, no crudo |
| 4 | flag `STACKY_RUN_SELECTION_PREFS_ENABLED = False` | `save` devuelve `False` y `load` devuelve `None` |
| 5 | trace de una corrida claude | tiene `tool == "claude_code_cli"` y `effort_mode == "nativo"` |
| 6 | trace de una corrida codex | tiene `tool == "codex_cli"` y `effort_mode == "presupuesto_turnos"` |
| 7 | trace con degradación | `requested_effort != effective_effort` y el dict lo refleja |
| 8 | `metadata_dict["model_effort"]` persiste tras `start_codex_cli_run` mockeado | presente y con las 4 claves |

> **Aviso duro:** el test 3 debe usar un `tmp_path` para el archivo de preferencias. La memoria del
> repo registra que un test del Plan 216 podía escribir en el **perfil REAL** del operador. Monkeypatcheá
> la ruta que usa `preferences._read/_write` (`preferences.py:25-37`) y verificá en el propio test que
> el archivo real **no** existe/no cambió.

**Comando de test:**
```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_plan264_selection_history.py" -q
```
(registrar en las dos `HARNESS_TEST_FILES`; correr 8-12 veces por el gotcha de SQLite).

**Criterio binario.** 8 passed × 10 corridas. Y:
```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -c "import sys; sys.path.insert(0,'Stacky Agents/backend'); from services.runtime_capabilities import EFFORT_MODE; print(sorted(EFFORT_MODE))"
```
imprime los 3 runtimes (KPI-5 estructural).

**Flag:** `STACKY_RUN_SELECTION_PREFS_ENABLED` (ON). El trace no lleva flag: es telemetría de solo
escritura local que el repo ya hace para Claude.
**Impacto por runtime:** los 3 persisten trace; Copilot registra `effort_mode="no_aplica"`.
**Trabajo del operador: ninguno.**

---

### F5 — Frontend: un solo selector, en todas las superficies

**Objetivo.** Cero selectores hechos a mano (KPI-4).

**(a) Extender el contrato del picker.** `Stacky Agents/frontend/src/services/modelEffortOptions.ts`
— agregar a `pickerCapabilities(catalog)` el `effort_note` y el `effort_mode` que ahora expone el
backend, para que la UI **diga la verdad** sobre lo que hace el esfuerzo en esa herramienta:

```diff
 export function pickerCapabilities(catalog: RuntimeModelCatalog | undefined) {
   return {
     showModels: ...,
     showEfforts: ...,
+    /** Plan 264 — "nativo" | "presupuesto_turnos" | "no_aplica". */
+    effortMode: catalog?.effort_mode ?? "nativo",
+    /** Plan 264 — frase que el backend manda para explicar la degradación. */
+    effortNote: catalog?.effort_note ?? null,
   };
 }
```
y en `components/ModelEffortPicker.tsx`, renderizar `effortNote` como texto de ayuda debajo del select
de esfuerzo cuando `effortMode !== "nativo"`.

> **Se conserva la decisión de diseño del Plan 212 F4** (documentada en `ModelEffortPicker.tsx:12-18`):
> **se ofrecen TODOS los efforts, siempre**, anotando a qué degradan. No los escondas ni los
> deshabilites. Este plan sólo agrega la nota de *modo*, no cambia esa regla.

**(b) Reemplazar los 2 selectores hechos a mano:**

| Archivo | Qué sacar | Qué poner |
|---|---|---|
| `Stacky Agents/frontend/src/pages/PlansBoardPage.tsx` | el `<select>` de modelos de `:341` y la lógica de `:150-159` (`setActionModel`, `setActionEffort`, `availableEfforts`, `effortsForModel`) | `<ModelEffortPicker catalog={claudeCat} model={actionModel} effort={actionEffort} onChange={...} />` |
| `Stacky Agents/frontend/src/components/IncidentResolverModal.tsx` | la lógica de `:83-96` (`claudeModels`, `claudeEfforts`, `claudeDefaultModel`, el default desde `EMERGENCY_MODEL_CATALOG`) y sus `<select>` | el mismo `<ModelEffortPicker>`, alimentado por `useModelCatalog()` |

> El envío sigue igual: `IncidentResolverModal.tsx:243-244` ya manda `model` y `effort` al backend.
> **No cambies el contrato del POST**, sólo de dónde salen los valores.

**(c) Agregar el picker donde no había** (las superficies de F3 que ahora aceptan selección):
`components/devops/DeploymentsSection.tsx`, `components/devops/TriggerPipelineSection.tsx` y
`pages/DocsPage.tsx`, sólo si esas pantallas efectivamente lanzan una corrida —
**verificalo leyendo cada archivo antes de agregar nada**. Si una no lanza corridas, no le pongas
selector: un selector que no hace nada es peor que ninguno.

**Tests (vitest, lógica pura):** crear
`Stacky Agents/frontend/src/services/__tests__/modelEffortOptions.plan264.test.ts`:

| # | Caso | Aserción |
|---|---|---|
| 1 | `pickerCapabilities(undefined)` | no lanza; `effortMode === "nativo"` |
| 2 | catálogo con `effort_mode: "no_aplica"` | `showEfforts === false` |
| 3 | catálogo con `effort_mode: "presupuesto_turnos"` | `effortNote` no nulo |
| 4 | `buildEffortOptions` con un modelo que degrada | sigue devolviendo **los 5** efforts, con la anotación (regresión del Plan 212 F4) |

```powershell
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/modelEffortOptions.plan264.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/modelCatalogFallback.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```

> **Corré cada archivo de test por separado.** La suite completa de vitest de este repo tiene
> contaminación cross-file conocida.

**Criterio binario.** Los 3 comandos exit 0, y el grep de KPI-4:
```bash
grep -rn "<select" --include=*.tsx "Stacky Agents/frontend/src/pages/PlansBoardPage.tsx" "Stacky Agents/frontend/src/components/IncidentResolverModal.tsx" | grep -icE "model|effort"
```
debe dar **0**.

**Restricciones de ratchet (duras):** no aumentar `style={{` en los archivos tocados
(`PlansBoardPage.tsx` está congelado en **3** en `frontend/src/__tests__/uiDebtBaseline.json`), y
**cero literales hex nuevos** en CSS.

**Flag:** `STACKY_MODEL_PICKER_EVERYWHERE_ENABLED` (ON). El estado de la flag se lee de
**`/api/diag/health`**, que es donde ya viven las flags de UI.
**Impacto por runtime:** el picker se auto-adapta por `effort_mode`: Claude muestra esfuerzo,
Codex lo muestra con la nota de presupuesto de turnos, Copilot **no lo muestra**.
**Trabajo del operador: ninguno** (todo preseleccionado por catálogo/preferencia).

---

### F6 — Frontend: el historial dice qué se usó

**Objetivo.** Que el operador vea, por corrida, herramienta + modelo + esfuerzo pedido y efectivo.

**Archivos a editar (2):**

1. `Stacky Agents/frontend/src/components/ExecutionDetailDrawer.tsx` — mostrar
   `metadata.model_effort` con las claves de F4 (`tool`, `requested_model`, `effective_model`,
   `requested_effort`, `effective_effort`, `effort_mode`). Si `requested_* !== effective_*`, marcarlo
   con el `ModelDecisionChip` **ya existente** (`components/ModelDecisionChip.tsx`) — no crees un chip
   nuevo.
2. `Stacky Agents/frontend/src/pages/PlansBoardPage.tsx:482-483` — el historial de corridas ya muestra
   `r.model` y `r.effort`; agregar la **herramienta** (`r.tool ?? "—"`) como tercera columna.

**Test:** crear `Stacky Agents/frontend/src/services/__tests__/modelEffortTrace.test.ts` sobre un
helper puro nuevo `formatModelEffortTrace(trace)` en
`Stacky Agents/frontend/src/services/modelEffortTrace.ts`:

| # | Caso | Aserción |
|---|---|---|
| 1 | trace `undefined`/`null` | devuelve `null`, no lanza |
| 2 | trace sin degradación | `degraded === false`, texto sin flecha |
| 3 | trace con `requested_effort: "max"`, `effective_effort: "high"` | `degraded === true` y el texto contiene `"max → high"` |
| 4 | trace con `effort_mode: "no_aplica"` | el texto dice que la herramienta no usa esfuerzo |
| 5 | trace de un deploy viejo (sin `tool`) | no lanza; `tool` se muestra como `"—"` |

```powershell
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/modelEffortTrace.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```

**Criterio binario.** 5 passed, `tsc` exit 0, `grep -c "style={{" PlansBoardPage.tsx` sigue en **3**.
**Flag:** protegido por las flags de las pantallas que lo contienen (ya ON).
**Impacto por runtime:** los 3 se muestran; Copilot muestra "no aplica" en esfuerzo.
**Trabajo del operador: ninguno.**

---

### F7 — Cierre y verificación consolidada

**Comandos (todos deben salir exit 0):**

```powershell
$py = "Stacky Agents\backend\.venv\Scripts\python.exe"
& $py -m pytest "Stacky Agents\backend\tests\test_plan264_runtime_capabilities.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_plan264_codex_effort_parity.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_plan264_run_selection.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_plan264_selection_history.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_runtime_dispatch.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_runtime_metadata_roundtrip.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_plan212_requested_vs_effective.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_plan212_model_probe.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_harness_flags.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_harness_ratchet_meta.py" -q
& $py -m compileall -q "Stacky Agents\backend\services" "Stacky Agents\backend\api"
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/modelEffortOptions.plan264.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/modelEffortTrace.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```

> Los tests `test_plan212_*` son la regresión del plan que construyó la matriz. Si se ponen rojos, este
> plan rompió su contrato ⇒ arreglalo, **no** lo agregues a una allowlist.

**Criterio binario.** 14 comandos exit 0 + los 3 greps de KPI-1, KPI-2 (test 9 de F3) y KPI-4.
**Trabajo del operador: ninguno.**

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Prob. | Mitigación |
|---|---|---|---|
| **R1** | Ciclo de import: `runtime_capabilities` ← `claude_code_cli_runner` ← `model_catalog._merge_probe` (que ya importa `claude_code_cli_runner` en `model_catalog.py:135`). | **Alta** | `runtime_capabilities` importa `model_catalog` y `llm_router` **sólo dentro de funciones**, nunca a nivel de módulo. El comando de verificación de imports de F1 es obligatorio y va **antes** de seguir. |
| **R2** | Honrar el effort en Codex hace que corridas que antes eran baratas ahora gasten más turnos. | Media | Es el comportamiento **pedido y correcto** (el operador eligió ese esfuerzo). Se mitiga con: (a) el override explícito manda, no el adaptativo; (b) `CODEX_EFFORT_TURNS` tope `+3`; (c) la flag `STACKY_CODEX_EFFORT_PARITY_ENABLED` permite volver atrás sin deploy. Medir el delta de costo con el Centro de Costos existente tras 1 semana. |
| **R3** | El `clamp_model` capa Opus a Sonnet y el operador cree que corre Opus. | Media | `clamp_selection` devuelve `degraded: True` + `reason`, y F6 lo muestra con `ModelDecisionChip`. La degradación deja de ser silenciosa. |
| **R4** | Tocar `variant_generator.py` (call site 7 de F3) pisa trabajo sin commitear de una sesión paralela. | **Alta** (el repo tiene sesiones concurrentes) | `git status --porcelain` antes de cada archivo; si está sucio y no es tuyo, **saltear y registrar**. Prohibido `stash`/`reset`/`checkout --`. |
| **R5** | Reemplazar el selector de `IncidentResolverModal` rompe el flujo del Dev Resolutor. | Media | El contrato del POST (`:243-244`) **no se toca**. Smoke manual obligatorio: abrir la bandeja, lanzar un resolutor, verificar en el detalle de la ejecución que `model_effort.tool` y `effective_effort` son los elegidos. |
| **R6** | El test 9 de F3 (AST) se vuelve frágil y bloquea call sites legítimos. | Media | Es AST, no regex (la memoria del repo registra que un centinela textual rompió el motor de flags). Excluye `evals/` y `tests/`. Admite **una sola** entrada de allowlist, con motivo escrito. |
| **R7** | `test_harness_flags_help` sale rojo. | Media | **Tiene 4 fallos ajenos preexistentes.** Validá sólo que tus 4 flags nuevas tengan `label`/`description` no vacíos; no adoptes los rojos ajenos. |
| **R8** | Los tests que tocan la DB salen flaky (`SQLITE_LOCKED`). | **Alta** | Correr **por archivo**, 8-12 veces. Nunca la suite completa. |

---

## 7. Fuera de scope

- **No** se agregan modelos ni runtimes nuevos al catálogo: se consume el que hay.
- **No** se toca `services/adaptive_selector.py` (sigue proponiendo el piso).
- **No** se cambia `CLAUDE_CAP_MODEL` ni la política de `allow_opus` del `llm_router`.
- **No** se toca el `copilot_bridge` ni se le inventa un esfuerzo a GitHub Copilot Pro.
- **No** se persiste preferencia por usuario (mono-operador): la clave es por **proyecto**.
- **No** se migra el catálogo a base de datos: sigue en `config/model_catalog.json`.
- **No** se agrega un selector a pantallas que no lanzan corridas.

---

## 8. Orden de implementación y DoD

**Orden (estricto):**

1. **F0** — flags.
2. **F1** — `runtime_capabilities.py` + deduplicación (todo lo demás lo consume). **Verificar imports antes de seguir.**
3. **F2** — paridad de Codex (el bug más grave; independiente de F3).
4. **F3** — `resolve_run_selection` + los 10 call sites.
5. **F4** — persistencia + trace en los 3 runtimes.
6. **F5** — un solo selector en el frontend (necesita el `effort_mode` de F1/F4 en el contrato del catálogo).
7. **F6** — historial visible.
8. **F7** — cierre.

**Definición de Hecho (DoD):**

- [ ] Los 14 comandos de F7 salen **exit 0**, cero rojos.
- [ ] **KPI-1**: el grep de literales de efforts fuera de `runtime_capabilities.py` ⇒ **0**.
- [ ] **KPI-2**: el test AST de F3 pasa; a lo sumo **1** entrada de allowlist, con motivo escrito.
- [ ] **KPI-3**: `test_plan264_codex_effort_parity.py` verde **10 corridas seguidas**.
- [ ] **KPI-4**: el grep de `<select>` de modelo/effort en las 2 pantallas ⇒ **0**.
- [ ] **KPI-5**: `EFFORT_MODE` cubre los 3 runtimes y el trace se persiste en los 3.
- [ ] Las 4 flags declaran default explícito (**las 4 ON**), y el plan deja escrito por qué ninguna cae
      en categoría (A) ni (B).
- [ ] Los 4 archivos `tests/test_plan264_*.py` registrados en **ambas** listas `HARNESS_TEST_FILES`;
      `test_harness_ratchet_meta.py` verde.
- [ ] `compileall` de `services/` y `api/` exit 0 (sin ciclos de import).
- [ ] Ningún símbolo público borrado: `_clamp_effort_for_model`, `CLI_VALID_EFFORTS`,
      `build_model_effort_trace` siguen existiendo (aunque deleguen).
- [ ] `style={{` no aumentó en los `.tsx` tocados; cero literales hex nuevos.
- [ ] Smoke manual del Dev Resolutor hecho (R5) y anotado.
- [ ] Registro de implementación agregado al final de **este** documento, con la salida real y los
      call sites que quedaron pendientes por trabajo ajeno.
- [ ] `git commit` con **pathspec explícito** (`git commit -- "<ruta>" ...`). Prohibido `git add -A`,
      `reset`, `amend`, `stash` y `--no-verify`. El `push` es manual.
