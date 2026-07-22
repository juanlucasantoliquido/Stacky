# Plan 212 — Selector vivo de modelo y effort en tickets ADO, y cumplimiento REAL de la elección

> Estado: **v1 · PROPUESTO** (2026-07-22). Pipeline: **[este paso ✓]** → criticar (`criticar-y-mejorar-plan`) → implementar (`implementar-plan-stacky`) → supervisar.
> Autor: StackyArchitectaUltraEficientCode (perfil max, heredado de Opus 4.8). Sin modelos menores en la elaboración (directiva del operador).
> Runtimes objetivo: Codex CLI, Claude Code CLI, GitHub Copilot Pro (paridad obligatoria; el núcleo NO usa LLM).
> Origen: **incidencia reportada por el operador** — *"En los tickets ADO, cuando selecciono Claude Code me debe dar la lista de todos los modelos disponibles al momento con todos los efforts disponibles."*

---

## Planes relacionados (leer antes de implementar)

- **EXTIENDE Plan 159** — "Catálogo unificado de modelos/efforts (dinámico)" (`Stacky Agents/docs/159_*`, IMPLEMENTADO F0-F6, MERGEADO `8593b34f`). El 159 creó la fuente única (`services/model_catalog.py`, `config/model_catalog.json`, `GET /api/agents/model-catalog`, `hooks/useModelCatalog.ts`, `services/modelCatalogFallback.ts`). **Este plan NO lo reimplementa**: lo consume, lo completa (F3), le agrega frescura (F5) y descubrimiento vivo (F6). Todo lo que el 159 congeló (shape del endpoint, nombre de la flag `STACKY_MODEL_CATALOG_ENABLED`, `resolveModelCatalog`) se respeta.
- **COMPLEMENTA Plan 43** — "Generador de épicas config-auto + selector modelo/effort" (F0/F1 en código: `_clamp_effort_for_model`, `clamp_model(allow_opus=)`). Este plan **cierra el agujero que dejó el 43**: el `allow_opus=True` del endpoint se deshace río abajo en el runner (§2.1). No cambia la política (Opus sigue restringido a `_OPUS_ALLOWLIST`), solo hace que la política **se cumpla de punta a punta**.
- **HABILITA Plan 196** — "Gestor de planes accionable + selector dinámico modelo/effort" (`docs/196_*`, CRITICADO v2, SIN implementar). El 196 necesita un selector modelo/effort en `/planes`; F4 de este plan entrega el componente único `ModelEffortPicker.tsx` que el 196 debe **consumir en vez de crear el suyo**. Si el 196 se implementa primero, quien implemente 212 F4 **integra** (no duplica) y migra el selector del 196 al componente compartido. Verificación tras merge: `grep -rn "ModelEffortPicker" "Stacky Agents/frontend/src"` → 1 definición + N usos, **cero** selectores `<select>` de modelo Claude fuera de ese componente (sentinel de F4).
- **NO colisiona con 208/210/211.** 208 toca `api/tickets.py::_apply_task_state` y el daemon de completion; 210/211 tocan `harness/post_run.py` y el deliverable del developer. Este plan toca `api/agents.py` (endpoint `run`), `services/llm_router.py`, `services/claude_code_cli_runner.py` (bloque de routing) y frontend de selección. **Cero archivos compartidos con 208/210/211 salvo `backend/scripts/run_harness_tests.sh|.ps1`** (ratchet, siempre aditivo: agregar líneas propias, nunca reordenar las ajenas).

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** Hoy, cuando el operador lanza un agente sobre un ticket ADO desde el tablero, **no existe ningún selector de modelo ni de effort**: el board solo deja elegir *runtime* (`TicketBoard.tsx:188-202`) y el comentario del propio código lo admite en texto (`TicketBoard.tsx:394-396`, *"Sin selector de modelo/effort por-run en el board"*). Donde sí hay selector (dos modales), la lista sale de un archivo estático fechado el **2026-07-17** (`config/model_catalog.json:3`), un modal **oculta** los efforts para runtimes no-Claude y el otro los **deshabilita** por modelo — es decir, jamás se ven "todos los efforts". Y lo más grave: **aunque el operador elija Opus 4.8, el runtime CLI corre Sonnet 5**, porque el `allow_opus=True` que aplica el endpoint se deshace en el router del runner (§2.1). Este plan (a) pone un **selector único, completo y vivo** de modelo+effort en el punto donde se lanza el trabajo sobre tickets ADO, (b) hace que **la elección se cumpla de verdad** hasta el argumento `--model`/`--effort` del CLI, (c) abre el **canal de effort** en `/api/agents/run` (hoy inexistente en el contrato del API) y (d) agrega **descubrimiento vivo sin costo de tokens** para que "los modelos disponibles al momento" no sean una foto congelada de un JSON.

**Gap que cierra.** Convierte la selección de modelo/effort de una **promesa parcial y desmentida por el runtime** en un **contrato verificable de punta a punta**: lo que el operador elige es lo que la máquina ejecuta, y lo que el catálogo ofrece es lo que el CLI instalado realmente acepta.

**KPI / impacto medible (binarios).**
- **KPI-1 — Cero degradación silenciosa de modelo:** para todo run con override explícito de un modelo permitido, `--model <id>` en el comando spawneado == el id elegido. Medible con el test de F1 y el log `router → <modelo> (<razón>)` (`claude_code_cli_runner.py:852`): **cero** ocurrencias de `user-override claude-opus-4-8 -> clamp` cuando el operador eligió Opus desde el selector.
- **KPI-2 — Effort honrado en el flujo estándar:** `POST /api/agents/run` con `effort` produce `--effort <valor efectivo>` en el comando. Hoy: **imposible** (el parámetro no existe en el contrato — `endpoints.ts:1140-1159`, `api/agents.py:506-522`). Meta: 100% de los runs con effort elegido lo reflejan en el comando.
- **KPI-3 — Catálogo completo visible:** el selector muestra **todos** los modelos del catálogo y **los 5 efforts** (`low/medium/high/xhigh/max`), sin ocultar ni deshabilitar; los no soportados por el modelo se muestran anotados con su equivalencia efectiva. Medible: test de F4 que cuenta opciones renderizadas == cardinalidad del catálogo.
- **KPI-4 — Cero drift de la matriz de efforts:** la matriz modelo×effort está hoy **triplicada** (`model_catalog.json:22-27`, `api/agents.py:588-605`, `claude_code_cli_runner.py:2134`). Meta: test de paridad verde que falla ante cualquier divergencia futura.
- **KPI-5 — Frescura observable:** el selector muestra la antigüedad del catálogo y permite refrescarlo sin recargar la página (hoy la caché de promesa module-level lo hace imposible — `useModelCatalog.ts:12-19`). Meta: 1 click → catálogo re-consultado.
- **KPI-6 — Cero regresión:** con todas las flags nuevas en OFF, el comportamiento es byte-idéntico al actual y la suite existente pasa sin cambios.

---

## 2. Por qué ahora / gap que cierra (anclado en evidencia verificada)

Cada ancla `archivo:línea` fue **releída contra el repo el 2026-07-22** (no se cita de memoria). Rutas relativas a `Stacky Agents/`.

### 2.1 El agujero grave: elegir Opus 4.8 no ejecuta Opus 4.8 (degradación silenciosa)

Cadena verificada, en orden de ejecución:

1. El endpoint permite Opus explícitamente: `backend/api/agents.py:700`, `:946`, `:1136` → `_llm_router.clamp_model(_base_model, allow_opus=True)`.
2. El valor llega al runner como `model_override`.
3. El runner **vuelve a routear** y pasa el override al router: `backend/services/claude_code_cli_runner.py:840-850` → `llm_router.decide(..., override=model_override or (config.CLAUDE_CODE_CLI_MODEL or None), backend="anthropic", ...)`.
4. **`decide()` NO tiene parámetro `allow_opus`** — firma completa en `backend/services/llm_router.py:188-196`.
5. Dentro de `decide()`: `backend/services/llm_router.py:233-241` →
   ```python
   if override:
       capped = clamp_model(override)          # ← allow_opus=False por default
       if capped != override:
           return RoutingDecision(model=capped, reason=f"user-override {override} -> clamp §5.2 ({capped})")
   ```
   Con `_FORBIDDEN_CLAUDE_TIER = ("opus", "fable")` (`llm_router.py:33`) y `CLAUDE_CAP_MODEL = "claude-sonnet-5"` (`llm_router.py:32`), `claude-opus-4-8` → **`claude-sonnet-5`**.
6. Ese valor clampeado es el que se spawnea: `routed_model = decision.model` (`claude_code_cli_runner.py:851`) → `_spawn_claude_with_fallback(primary_model=routed_model, build_cmd=_build_cli_command, ...)` (`:905-908`) → `_build_command(model_override=model_for_attempt, ...)` (`:883-891`) → `cmd.extend(["--model", model])` (`:2126-2127`).

**Conclusión:** el catálogo ofrece Opus 4.8 (`config/model_catalog.json:11`), el modal lo deja elegir (`frontend/src/components/EpicFromBriefModal.tsx:487-501`), el endpoint lo autoriza — y el CLI corre Sonnet 5. **El comentario del propio runner ya declara la intención vieja**: *"decide() aplica el cap duro (clamp_model): jamás opus/fable, ni por override"* (`claude_code_cli_runner.py:807`), que contradice al Plan 43. El test que debería haberlo atrapado se detiene un nivel antes: `backend/tests/test_llm_router_opus_flag.py:82-95` asserta `kwargs["model_override"] == "claude-opus-4-8"` en la llamada a `run_agent`, **nunca llega a `_build_command`**.

### 2.2 En la vista de tickets ADO no hay selector de modelo/effort

- `frontend/src/pages/TicketBoard.tsx:188-202` — el `RunModal` monta **solo** `<AgentRuntimeSelector>` + la leyenda "Lanzará con: …". No hay `<select>` de modelo ni de effort.
- `frontend/src/pages/TicketBoard.tsx:394-402` — comentario literal en el código: *"Sin selector de modelo/effort por-run en el board (mismo patrón que handleRunConfirm arriba, que tampoco pasa model_override): el backend usa su default/selector adaptativo."*
- `frontend/src/components/AgentLaunchModal.tsx:305-310` (asignar ticket desde el equipo) — mismo hueco: solo runtime.
- Consecuencia directa: la incidencia del operador es **literal y correcta** — en tickets ADO no se puede elegir modelo ni effort.

### 2.3 El canal de effort no existe en el contrato del flujo estándar

- `backend/api/agents.py:506-522` — `POST /api/agents/run` llama `agent_runner.run_agent(...)` pasando `model_override` pero **nunca** `effort_override`, pese a que `run_agent` lo acepta (`backend/agent_runner.py:87`).
- `frontend/src/api/endpoints.ts:1140-1159` — el tipo del payload de `runWithOptions` no declara `effort`.
- `frontend/src/services/agentLaunch.ts:127-141` — `launchAgentWithRuntime` acepta `modelOverride` pero **no** effort.
- Es decir: aun agregando un `<select>` en el board, hoy **no habría por dónde mandar el valor**.

### 2.4 "Todos los efforts" no se ven nunca

- `frontend/src/components/IncidentResolverModal.tsx:408` — el bloque completo de modelo+effort se **oculta** salvo `agentRuntime === "claude_code_cli"`; y `:420-424` lista los efforts **sin filtrar** por modelo (no anota nada).
- `frontend/src/components/EpicFromBriefModal.tsx:506-513` — los efforts no soportados se renderizan `disabled` con el sufijo *"(no disponible para este modelo)"*. Con Sonnet 5 (default) eso **deshabilita `xhigh`**; con Haiku deshabilita `xhigh` **y** `max`.
- Los dos modales divergen entre sí (uno filtra, el otro no) → misma pantalla, dos comportamientos.

### 2.5 El catálogo es una foto estática que puede envejecer

- `backend/config/model_catalog.json:3` → `"updated_at": "2026-07-17"`; `:6` → `"source": "static_config_file"`. Los 4 modelos están hardcodeados en `:9-14`.
- La única introspección viva del repo es de GitHub Copilot (`services/model_catalog.py:85-105` → `copilot_bridge.list_copilot_models`), declarado en `model_catalog.json:41` (`"source": "live_introspection"`).
- `frontend/src/hooks/useModelCatalog.ts:12-19` — caché de **promesa module-level**: un único fetch por sesión de página. Si el primer fetch falla, el selector queda en fallback de emergencia **hasta un F5 del navegador**.
- `frontend/src/services/modelCatalogFallback.ts:7-20` — ese fallback trae **3 modelos y 1 solo effort (`medium`)**. Es exactamente el síntoma "no me muestra todo".

### 2.6 La matriz modelo×effort está triplicada (drift garantizado)

1. `backend/config/model_catalog.json:22-27` (`effort_support`).
2. `backend/api/agents.py:588-605` (`_clamp_effort_for_model`, degradación server-side).
3. `backend/services/claude_code_cli_runner.py:2134` (set plano `("low","medium","high","xhigh","max")`, sin matriz por modelo).

Hoy coinciden; nada garantiza que sigan coincidiendo. No existe test de paridad (verificado: no hay ningún test que compare las tres fuentes).

---

## 3. Principios y guardarraíles (no negociables)

- **G1 — Paridad de 3 runtimes.** El núcleo (catálogo, contrato del endpoint, componente de selección) es común. Claude Code CLI: modelo + effort reales. Codex CLI: modelo "Automático" y **sin efforts** (`model_catalog.json:36-38`; el nivel se traduce a presupuesto de turnos) → el selector muestra el runtime con su nota, deshabilitado y explicado, **nunca vacío ni engañoso**. GitHub Copilot: modelos por introspección viva ya existente, sin efforts. Fallback de cada uno: catálogo de emergencia completo (F3).
- **G2 — Human-in-the-loop.** El plan **amplifica** al operador: le muestra opciones reales y honra su elección. No decide por él, no auto-cambia modelos, no publica nada. El selector adaptativo existente (`services/adaptive_selector.py`) sigue actuando **solo cuando el operador no eligió**.
- **G3 — Cero trabajo extra al operador.** Todo default preserva el comportamiento actual: si no toca el selector, el sistema hace exactamente lo de hoy. La preferencia se recuerda (F4) — el operador elige una vez, no en cada run.
- **G4 — No aflojar la política de modelos.** `clamp_model` sigue siendo la **única** función que decide qué está capado (`llm_router.py:38-57`) y `_OPUS_ALLOWLIST` sigue siendo `{"claude-opus-4-8"}`. Este plan **no agrega ni un modelo** a la allowlist: hace que el permiso ya otorgado por el Plan 43 llegue a destino. `fable` y cualquier Opus fuera de la allowlist siguen capados.
- **G5 — Guardarraíl 11 intacto (DevOps nunca Opus).** El desbloqueo de F1 se activa **exclusivamente** desde un `model_override` explícito por-run que ya pasó el clamp del endpoint. El agente DevOps clampea con `allow_opus=False` en su endpoint (test vivo: `backend/tests/test_plan90_devops_agent_endpoints.py:147`), así que su `model_override` nunca puede ser Opus. El default global `CLAUDE_CODE_CLI_MODEL` **no** desbloquea Opus (§F1, decisión explícita).
- **G6 — Cero costo de tokens ociosos.** El descubrimiento vivo (F6) **no invoca ningún modelo**: solo ejecuta subcomandos de listado del CLI con timeout corto y parseo JSON. Ningún prompt, ningún turno. (Directiva del operador: flags ON por default salvo las que quemen tokens ociosos — esta no quema ninguno.)
- **G7 — Degradación explícita, nunca silenciosa.** Si el modelo o el effort efectivo difiere del elegido, el sistema lo **dice** (log + badge en UI, F7). Prohibido "arreglarlo por atrás" sin avisar — es la causa raíz de esta incidencia.
- **G8 — Config del operador vía UI.** Toda flag nueva se registra en `harness_flags.py` (visible/editable desde la UI de flags), nunca env-only.
- **G9 — Backward-compatible.** Todo parámetro nuevo es opcional con default que reproduce el comportamiento actual. Ningún test existente se modifica salvo los que este plan corrige por ser incorrectos (ninguno identificado hoy).

> Convención de tests: **backend** = pytest **por archivo** con el intérprete del backend; **frontend** = vitest **por archivo** (contaminación cross-file conocida — memoria `gotcha-vitest-test-order-pollution-frontend`).
> **Comando backend** (desde `Stacky Agents/backend`): `& ".venv\Scripts\python.exe" -m pytest tests\<archivo> -q` — si `.venv` no existe, usar `venv\Scripts\python.exe` (mismo py3.13).
> **Comando frontend** (desde `Stacky Agents/frontend`): `npx vitest run src\<ruta>\<archivo>.test.ts`.
> **Ratchet de tests:** todo `backend/tests/test_*.py` nuevo se registra en `backend/scripts/run_harness_tests.sh` (array `HARNESS_TEST_FILES=(` en `:20`, entradas **sin** comillas) **y** en `backend/scripts/run_harness_tests.ps1` (array `$HarnessTestFiles = @(` en `:13`, entradas **con** comillas). Si falta, el meta-test `backend/tests/test_harness_ratchet_meta.py:43-53` se pone rojo.

---

## 4. Fases

### F0 — Tests de caracterización: dejar por escrito los 3 agujeros

**Objetivo (1 frase).** Escribir primero los tests que hoy fallan y que solo pueden ponerse verdes si el plan se implementa de verdad (anti falso-verde).

**Archivo a crear:** `Stacky Agents/backend/tests/test_plan212_characterization.py`

**Casos exactos (todos deben estar ROJOS antes de F1-F3):**

| # | Nombre del test | Qué asserta | Estado hoy |
|---|---|---|---|
| 1 | `test_decide_accepts_allow_opus_and_keeps_opus` | `llm_router.decide(agent_type="business", blocks=[], override="claude-opus-4-8", backend="anthropic", allow_opus=True).model == "claude-opus-4-8"` | ROJO — `TypeError: decide() got an unexpected keyword argument 'allow_opus'` |
| 2 | `test_decide_without_allow_opus_still_clamps` | mismo llamado **sin** `allow_opus` → `.model == "claude-sonnet-5"` y `"clamp" in .reason` | VERDE hoy (es el ratchet de no-regresión de G4) |
| 3 | `test_run_endpoint_accepts_effort_and_propagates` | `POST /api/agents/run` con `{"effort": "high", ...}` → el spy sobre `agent_runner.run_agent` recibe `effort_override == "high"` | ROJO — el endpoint no lee `effort` |
| 4 | `test_run_endpoint_rejects_unknown_effort` | `POST /api/agents/run` con `{"effort": "ultra"}` → HTTP **400** y body con `error == "invalid_effort"` | ROJO |
| 5 | `test_effort_matrix_parity_catalog_vs_clamp` | para cada `model_id` de `model_catalog.json["runtimes"]["claude_code_cli"]["effort_support"]` y cada `effort` de `["low","medium","high","xhigh","max"]`: `_clamp_effort_for_model(effort, model_id) == effort` **si y solo si** `effort in effort_support[model_id]` | VERDE hoy (ratchet anti-drift, KPI-4) |
| 6 | `test_runner_effort_set_is_superset_of_catalog` | el set literal de `claude_code_cli_runner.py:2134` ⊇ unión de todos los `efforts` del catálogo | VERDE hoy (ratchet) |

**Detalle de implementación del caso 3/4 (para que no haya ambigüedad):** usar el patrón del test existente `backend/tests/test_run_brief_model_override.py` (mismo `app.test_client()`, mismo monkeypatch sobre `agent_runner.run_agent`). Leer ese archivo antes de escribir; **no inventar un harness nuevo**.

**Comando:** `& ".venv\Scripts\python.exe" -m pytest tests\test_plan212_characterization.py -q`
**Criterio de aceptación BINARIO:** al terminar F0, el comando reporta **exactamente 3 fallos** (casos 1, 3, 4) y 3 pasos. Al terminar F3, reporta **6 passed, 0 failed**.
**Registro en ratchet:** agregar `tests/test_plan212_characterization.py` a los dos scripts (ver convención en §3).
**Flag:** ninguna (son tests).
**Impacto por runtime:** ninguno (no toca runtime).
**Trabajo del operador:** ninguno.

---

### F1 — Que elegir Opus 4.8 ejecute Opus 4.8 (fin de la degradación silenciosa)

**Objetivo (1 frase).** Propagar el permiso `allow_opus` que el endpoint ya otorga hasta el router del runner, sin ampliar la política de modelos.

**Archivos a editar:**
1. `Stacky Agents/backend/services/llm_router.py`
2. `Stacky Agents/backend/services/claude_code_cli_runner.py`

**Cambio 1 — helper público (nuevo símbolo `is_opus_allowlisted`), insertar justo después de `clamp_model` (`llm_router.py:57`):**

```python
def is_opus_allowlisted(model: str | None) -> bool:
    """Plan 212 F1 — True si `model` es EXACTAMENTE un id de _OPUS_ALLOWLIST.

    Existe para que los callers (runner) no tengan que importar el set privado.
    No amplía la política: la allowlist sigue siendo la de llm_router.
    """
    return bool(model) and model in _OPUS_ALLOWLIST
```

**Cambio 2 — `decide()` acepta `allow_opus` (default `False` ⇒ byte-idéntico para todo caller existente).**
En la firma (`llm_router.py:188-196`), agregar como **último** parámetro keyword-only:

```python
    project_name: str | None = None,
    allow_opus: bool = False,          # Plan 212 F1 — default False conserva el cap global
) -> RoutingDecision:
```

Y en el bloque de override (`llm_router.py:233-241`) cambiar **una sola línea**:

```python
    if override:
-       capped = clamp_model(override)
+       capped = clamp_model(override, allow_opus=allow_opus)
```

Nada más de `decide()` se toca.

**Cambio 3 — el runner pide el permiso solo para overrides explícitos por-run.**
En `claude_code_cli_runner.py`, reemplazar el comentario obsoleto de `:807` y la llamada de `:840-850`:

```python
-        # decide() aplica el cap duro (clamp_model): jamás opus/fable, ni por override.
+        # Plan 212 F1 — decide() aplica el cap duro (clamp_model). El ÚNICO caso que
+        # se exime es un model_override EXPLÍCITO por-run cuyo id está en la
+        # allowlist de Opus (el endpoint ya lo autorizó con allow_opus=True,
+        # api/agents.py:700/:946/:1136). El default global CLAUDE_CODE_CLI_MODEL NO
+        # desbloquea Opus: evitaría el guardarraíl 11 (DevOps nunca Opus).
...
+        _allow_opus_for_run = llm_router.is_opus_allowlisted(model_override)
         decision = llm_router.decide(
             agent_type=agent_type or "",
             blocks=enriched_blocks,
             fingerprint_complexity=_cli_complexity,
             override=model_override or (config.CLAUDE_CODE_CLI_MODEL or None),
             backend="anthropic",
             project_name=project_name,
+            allow_opus=_allow_opus_for_run,
         )
```

**Decisión explícita y su razón (para el juez):** se desbloquea **solo** desde `model_override`, no desde `config.CLAUDE_CODE_CLI_MODEL`. Motivo: si el default global desbloqueara Opus, **todo** run del sistema —incluido el agente DevOps— pasaría a Opus con solo cambiar una config, rompiendo el guardarraíl 11 sin que nadie lo note. Contrapartida asumida: si el operador escribe `claude-opus-4-8` como default global, sus runs sin selección explícita seguirán corriendo Sonnet 5 — pero **eso deja de ser silencioso**: F7 lo muestra como "solicitado ≠ efectivo" con la razón exacta.

**Tests (TDD) — archivo `Stacky Agents/backend/tests/test_plan212_opus_end_to_end.py`:**

| Test | Assert |
|---|---|
| `test_decide_allow_opus_true_keeps_opus` | `decide(..., override="claude-opus-4-8", allow_opus=True).model == "claude-opus-4-8"` |
| `test_decide_allow_opus_false_clamps` | idem con `allow_opus=False` → `"claude-sonnet-5"` |
| `test_decide_allow_opus_true_still_blocks_fable` | `override="claude-fable-5", allow_opus=True` → `"claude-sonnet-5"` |
| `test_decide_allow_opus_true_still_blocks_opus_47` | `override="claude-opus-4-7", allow_opus=True` → `"claude-sonnet-5"` |
| `test_is_opus_allowlisted` | `True` solo para `"claude-opus-4-8"`; `False` para `None`, `""`, `"claude-sonnet-5"`, `"claude-opus-4-7"` |
| `test_runner_passes_allow_opus_only_for_explicit_override` | monkeypatch de `llm_router.decide` que captura kwargs; invocar el bloque de routing con `model_override="claude-opus-4-8"` → `kwargs["allow_opus"] is True`; con `model_override=None` y `config.CLAUDE_CODE_CLI_MODEL="claude-opus-4-8"` → `kwargs["allow_opus"] is False` |
| `test_build_command_receives_opus` | **el test que faltaba (KPI-1)**: con `model_override="claude-opus-4-8"`, el comando construido por `_build_command(model_override=<modelo ruteado>, ...)` contiene la pareja consecutiva `["--model", "claude-opus-4-8"]` |

> Para `test_build_command_receives_opus`, reusar el patrón de `backend/tests/test_adaptive_effort.py:95-126` (ya ejercita `_build_command` y asserta pares de flags). Leerlo antes de escribir.

**Comando:** `& ".venv\Scripts\python.exe" -m pytest tests\test_plan212_opus_end_to_end.py tests\test_llm_router_opus_flag.py tests\test_llm_router_cap.py tests\test_plan90_devops_agent_endpoints.py -q`
**Criterio BINARIO:** los 4 archivos verdes (los 3 últimos son la no-regresión de la política y del guardarraíl 11) **y** `grep -n "allow_opus" "Stacky Agents/backend/services/claude_code_cli_runner.py"` → 2+ matches.
**Flag que la protege:** **ninguna, a propósito.** Esto es la corrección de un bug de propagación de una decisión ya tomada por el Plan 43, no una feature nueva; una flag aquí solo agregaría un modo "roto" configurable. La política sigue protegida por `_OPUS_ALLOWLIST` (G4).
**Impacto por runtime:** Claude Code CLI = corrige la degradación. Codex CLI = sin efecto (no pasa por `llm_router.decide` con `backend="anthropic"`; su modelo es "Automático"). GitHub Copilot = sin efecto (rama `backend in ("copilot","vscode_bridge")`, `llm_router.py:249+`, intacta). Fallback: si `decide()` lanza, el runner ya cae a `clamp_model(routed_model)` (`claude_code_cli_runner.py:855`) — comportamiento conservador preservado.
**Trabajo del operador:** ninguno.

---

### F2 — Abrir el canal de effort en el flujo estándar (`/api/agents/run`)

**Objetivo (1 frase).** Que el effort elegido por el operador viaje desde el frontend hasta `--effort` del CLI en el flujo que usan los tickets ADO.

**Archivos a editar:**
1. `Stacky Agents/backend/api/agents.py`
2. `Stacky Agents/frontend/src/api/endpoints.ts`
3. `Stacky Agents/frontend/src/services/agentLaunch.ts`

**Cambio 1 — validación + propagación en el endpoint `run` (`api/agents.py`).** Insertar **antes** del bloque `try:` de `:505`:

```python
    # Plan 212 F2 — canal de effort del flujo estándar. Opcional y backward-compatible:
    # ausente/"" ⇒ None ⇒ el runner usa su default/adaptativo (comportamiento pre-212).
    _VALID_EFFORTS = ("low", "medium", "high", "xhigh", "max")
    _effort_raw = (payload.get("effort") or "").strip().lower()
    if _effort_raw and _effort_raw not in _VALID_EFFORTS:
        if _slot_held:
            from services import run_slots
            run_slots.release()
        return jsonify({
            "ok": False,
            "error": "invalid_effort",
            "valid": list(_VALID_EFFORTS),
        }), 400
    _effort_effective = (
        _clamp_effort_for_model(_effort_raw, payload.get("model_override"))
        if _effort_raw else None
    )
    if _effort_raw and _effort_effective != _effort_raw:
        logger.info(
            "plan212 effort degradado: solicitado=%s efectivo=%s modelo=%s",
            _effort_raw, _effort_effective, payload.get("model_override"),
        )
```

Y en la llamada a `run_agent` (`api/agents.py:506-522`), agregar **una línea** después de `model_override=...` (`:512`):

```python
             model_override=payload.get("model_override"),
+            effort_override=_effort_effective,                 # Plan 212 F2
```

> **Nota de orden importante:** `_clamp_effort_for_model` está definida en `api/agents.py:588`, **después** de la función `run`. En Python eso es válido (se resuelve en tiempo de ejecución, ambas viven en el mismo módulo). No moverla.
> **Nota de liberación de slot:** el early-return 400 debe liberar el slot de concurrencia si ya fue tomado (`_slot_held`, `api/agents.py:492-503`), igual que hacen los `except` de `:523-538`. Está contemplado arriba.

**Cambio 2 — contrato TS (`frontend/src/api/endpoints.ts:1140-1159`).** Agregar al tipo del payload de `runWithOptions`, después de `model_override`:

```ts
    model_override?: string | null;
+   /** Plan 212 — reasoning effort para runtimes que lo soportan (hoy: claude_code_cli).
+    *  Valores: "low"|"medium"|"high"|"xhigh"|"max". Omitido/null ⇒ default del backend. */
+   effort?: string | null;
```

**Cambio 3 — `launchAgentWithRuntime` (`frontend/src/services/agentLaunch.ts:127-175`).** Agregar el parámetro y propagarlo **solo** a `runWithOptions` (Copilot no tiene efforts — `model_catalog.json:45`):

```ts
   vscodeAgent?: VsCodeAgent | null;
   modelOverride?: string | null;
+  effort?: string | null;          // Plan 212 F2 — ignorado por github_copilot
 }) {
```
```ts
   return Agents.runWithOptions({
     ...
     model_override: modelOverride,
+    effort: effort ?? undefined,
```

**Tests (TDD):**
- Backend — `Stacky Agents/backend/tests/test_plan212_effort_channel.py`:
  - `test_run_accepts_effort_high` → spy sobre `run_agent`, `effort_override == "high"`.
  - `test_run_without_effort_passes_none` → `effort_override is None` (backward-compat).
  - `test_run_rejects_invalid_effort` → 400 + `error == "invalid_effort"` + `"low" in body["valid"]`.
  - `test_run_degrades_effort_for_model` → `{"effort": "xhigh", "model_override": "claude-sonnet-5"}` → `effort_override == "high"`.
  - `test_run_invalid_effort_releases_slot` → tras un 400, `run_slots.active_count()` vuelve al valor previo.
  - Comando: `& ".venv\Scripts\python.exe" -m pytest tests\test_plan212_effort_channel.py -q`
- Frontend — `Stacky Agents/frontend/src/services/__tests__/agentLaunchEffort.test.ts`:
  - `it("propaga effort a runWithOptions")` — mock de `Agents.runWithOptions`, assert `effort === "high"`.
  - `it("no rompe cuando effort es undefined")` — assert `effort === undefined`.
  - `it("no manda effort por openChat (copilot)")` — runtime `github_copilot` → el mock de `openChat` recibe un objeto **sin** la key `effort`.
  - Comando: `npx vitest run src\services\__tests__\agentLaunchEffort.test.ts`

**Criterio BINARIO:** ambos comandos verdes **y** `npx tsc --noEmit` sin errores nuevos.
**Flag que la protege:** ninguna. Es un parámetro **opcional y aditivo**: ausente ⇒ comportamiento idéntico al actual (G9). Una flag aquí no protegería nada porque el path viejo es exactamente "no mandar el campo".
**Impacto por runtime:** Claude Code CLI = effort real vía `--effort` (`claude_code_cli_runner.py:2132-2135`). Codex CLI = el backend acepta el campo y `run_agent` lo pasa; el runner de Codex **lo ignora** (no tiene flag `--effort`; ver nota en `model_catalog.json:38`) → el selector no ofrece efforts para Codex (F4) y el backend no falla si llegan. GitHub Copilot = no se envía.
**Trabajo del operador:** ninguno.

---

### F3 — Catálogo completo, honesto y sin drift

**Objetivo (1 frase).** Que el catálogo (y su fallback de emergencia) contenga **todo** lo disponible, y que la matriz modelo×effort tenga una sola verdad verificada por test.

**Archivos a editar:**
1. `Stacky Agents/backend/config/model_catalog.json`
2. `Stacky Agents/backend/services/model_catalog.py`
3. `Stacky Agents/frontend/src/services/modelCatalogFallback.ts`

**Cambio 1 — enriquecer el catálogo con la razón de la degradación (aditivo, no rompe el shape del 159).** Agregar a `claude_code_cli` una clave nueva **hermana** de `effort_support`, sin tocar las existentes:

```json
       "effort_support": { ... sin cambios ... },
+      "effort_degrade": {
+        "claude-haiku-4-5": {"xhigh": "high", "max": "high"},
+        "claude-sonnet-5": {"xhigh": "high"},
+        "claude-sonnet-4-6": {"xhigh": "high"},
+        "claude-opus-4-8": {}
+      },
+      "effort_note": "Los efforts no soportados por el modelo NO se ocultan: se ofrecen anotados con el valor que se aplicará realmente (ver effort_degrade). El backend degrada con _clamp_effort_for_model (api/agents.py:588)."
```

> `effort_degrade` debe ser **exactamente** el resultado de `_clamp_effort_for_model` para cada par (modelo, effort no soportado). El test de paridad de F0 caso 5 se extiende para verificarlo (ver abajo).

**Cambio 2 — fallback de emergencia backend completo (`services/model_catalog.py:26-40`).** Reemplazar `_EMERGENCY_FALLBACK` para que contenga **los 4 modelos y los 5 efforts** con el mismo `effort_support`/`effort_degrade` que el archivo. Regla dura: *el fallback de emergencia nunca puede ofrecer menos que el archivo*; si el archivo no se puede leer, el operador debe seguir viendo el catálogo completo.

**Cambio 3 — fallback de emergencia frontend (`frontend/src/services/modelCatalogFallback.ts:7-20`).** Hoy trae **3 modelos y 1 effort**. Reemplazar por los 4 modelos y los 5 efforts + `effort_support` + `effort_degrade`, espejando el backend. Mantener el comentario de "gemelo backend" (`:3-6`) y actualizarlo con la referencia al Plan 212.

**Cambio 4 — test de paridad (la parte que impide el drift futuro).**
Archivo: `Stacky Agents/backend/tests/test_plan212_effort_matrix_parity.py`

| Test | Assert |
|---|---|
| `test_catalog_matches_clamp_for_every_pair` | ∀ modelo ∈ `effort_support`, ∀ effort ∈ los 5: `_clamp_effort_for_model(effort, modelo) == effort` ⇔ `effort in effort_support[modelo]` |
| `test_effort_degrade_matches_clamp` | ∀ (modelo, effort) **no** soportado: `effort_degrade[modelo][effort] == _clamp_effort_for_model(effort, modelo)` |
| `test_runner_accepts_all_catalog_efforts` | la unión de ids de `efforts` del catálogo ⊆ el set literal de `claude_code_cli_runner.py:2134` (leído por `inspect.getsource` o por import del módulo y lectura de la constante si se extrae) |
| `test_emergency_fallback_is_not_poorer_than_file` | `len(_EMERGENCY_FALLBACK["claude_code_cli"]["models"]) >= len(archivo.models)` y lo mismo para `efforts` |
| `test_frontend_fallback_mirrors_backend` | parsea `frontend/src/services/modelCatalogFallback.ts` con regex sobre los ids (`/id:\s*"([^"]+)"/g`) y asserta que el set de ids de modelos y de efforts es **igual** al del `_EMERGENCY_FALLBACK` backend |

> Para `test_runner_accepts_all_catalog_efforts`, la forma más simple y robusta es **extraer el set a una constante nombrada** en el runner:
> en `claude_code_cli_runner.py`, arriba de `_build_command`, agregar `CLI_VALID_EFFORTS = ("low", "medium", "high", "xhigh", "max")` y cambiar `:2134` a `if effort in CLI_VALID_EFFORTS:`. El test importa la constante. Sin regex frágil.

**Comando:** `& ".venv\Scripts\python.exe" -m pytest tests\test_plan212_effort_matrix_parity.py tests\test_plan159_model_catalog_loader.py tests\test_plan159_model_catalog_endpoint.py tests\test_run_brief_efforts.py -q`
**Criterio BINARIO:** los 4 archivos verdes **y** `npx vitest run src\services\__tests__\modelCatalogFallback.test.ts` verde (test existente del 159, no debe romperse).
**Flag que la protege:** ninguna (es data + tests; el shape es aditivo y `resolveModelCatalog` ignora claves desconocidas).
**Impacto por runtime:** Claude = catálogo completo. Codex/Copilot = sus entradas del JSON no se tocan.
**Trabajo del operador:** ninguno.

---

### F4 — `ModelEffortPicker`: un solo selector, completo, en el punto donde se lanza el trabajo

**Objetivo (1 frase).** Un componente único que muestre **todos** los modelos y **todos** los efforts, y montarlo donde el operador lanza agentes sobre tickets ADO.

**Archivos a crear:**
- `Stacky Agents/frontend/src/components/ModelEffortPicker.tsx`
- `Stacky Agents/frontend/src/components/ModelEffortPicker.module.css`
- `Stacky Agents/frontend/src/components/modelEffortModel.ts` (**lógica pura, testeable sin DOM**)
- `Stacky Agents/frontend/src/components/__tests__/modelEffortModel.test.ts`

**Archivos a editar:**
- `Stacky Agents/frontend/src/pages/TicketBoard.tsx` (RunModal `:188-202`; `handleRunConfirm` `:323-329`; resolutor `:394-402`)
- `Stacky Agents/frontend/src/components/IncidentResolverModal.tsx` (reemplazar `:408-425`)
- `Stacky Agents/frontend/src/components/EpicFromBriefModal.tsx` (reemplazar `:487-514`)
- `Stacky Agents/frontend/src/store/workbench.ts` + `Stacky Agents/frontend/src/store/workbenchPure.ts`

**Modelo puro (`modelEffortModel.ts`) — 3 funciones exportadas, sin React:**

```ts
export interface EffortOption {
  id: string;            // "xhigh"
  label: string;         // "xhigh — muy alto"
  supported: boolean;    // según effort_support del modelo elegido
  effective: string;     // lo que realmente se aplicará ("high" si degrada)
  note: string;          // "" si supported; si no: "se aplicará como high (Sonnet 5 no soporta xhigh)"
}

/** TODOS los efforts del catálogo, anotados. NUNCA filtra ni deshabilita. */
export function buildEffortOptions(
  runtimeCatalog: RuntimeModelCatalog | undefined,
  modelId: string | null
): EffortOption[];

/** TODOS los modelos del catálogo, con el recomendado primero. */
export function buildModelOptions(
  runtimeCatalog: RuntimeModelCatalog | undefined
): { id: string; label: string; recommended: boolean }[];

/** Qué se ofrece por runtime. Fuente: el propio catálogo, no un if hardcodeado. */
export function pickerCapabilities(
  runtimeCatalog: RuntimeModelCatalog | undefined
): { showModels: boolean; showEfforts: boolean; note: string };
```

Reglas exactas de `buildEffortOptions` (para que no haya interpretación):
1. Recorre `runtimeCatalog.efforts` **en el orden del catálogo** (no reordena).
2. `supported = (runtimeCatalog.effort_support?.[modelId] ?? []).includes(id)`; si `effort_support` no tiene entrada para ese modelo (o `modelId` es null), `supported = true` y `note = ""` (optimista: el backend clampea igual).
3. `effective = supported ? id : (runtimeCatalog.effort_degrade?.[modelId]?.[id] ?? id)`.
4. `note = supported ? "" : \`se aplicará como ${effective}\``.
5. **Ninguna opción se omite y ninguna se marca `disabled`.** (Esto es la incidencia literal del operador: quiere ver *todos* los efforts.)

Reglas de `pickerCapabilities`:
- `showModels = (runtimeCatalog?.models?.length ?? 0) > 0`
- `showEfforts = (runtimeCatalog?.efforts?.length ?? 0) > 0`
- `note = runtimeCatalog?.note ?? ""` (para Codex se muestra su nota real del JSON: *"Codex CLI no soporta --effort como flag…"*).
- Con esto, **no hay ningún `if runtime === "claude_code_cli"` hardcodeado en la UI**: el comportamiento por runtime sale del catálogo. Es lo que hace que el componente sea correcto en los 3 runtimes por construcción (G1).

**Componente `ModelEffortPicker.tsx` — contrato de props:**

```tsx
interface ModelEffortPickerProps {
  runtime: AgentRuntime;
  model: string | null;
  effort: string | null;
  onChange: (next: { model: string | null; effort: string | null }) => void;
  disabled?: boolean;
  /** "inline" (fila compacta en modales) | "block" (dos filas con labels) */
  variant?: "inline" | "block";
}
```
Comportamiento:
- Usa `useModelCatalog()` (F5 le agrega `refresh`/`updatedAt`).
- Si `showModels` es false para el runtime → renderiza la `note` del catálogo en texto llano, sin selects (nunca un select vacío).
- Al cambiar de modelo **no resetea el effort**: lo mantiene y actualiza su anotación (la degradación la hace el backend y se muestra). Esto elimina el reset silencioso de `EpicFromBriefModal.tsx:169-175`.
- Muestra debajo, en una línea: `Se ejecutará: <modelo> · effort <effective>` — la verdad efectiva (G7).

**Persistencia de la elección (cero trabajo repetido — G3).** En `store/workbench.ts`:
- Agregar al estado: `agentModel: string | null` (default `null`) y `agentEffort: string | null` (default `null`), con setters `setAgentModel` / `setAgentEffort` (mismo patrón que `setAgentRuntime`, `:134`).
- Agregarlos a `partialize` (`:148-152`) junto a `agentRuntime`.
- **Bumpear `WORKBENCH_PERSIST_VERSION`** y extender `migrateWorkbenchPersist` en `store/workbenchPure.ts` para que una versión vieja rehidrate con `agentModel: null, agentEffort: null` (nunca `undefined`). Actualizar `store/workbenchPure.test.ts` con un caso nuevo para la versión nueva. **Sin este paso, la rehidratación de un localStorage viejo deja las keys ausentes** — es la trampa clásica de este store.

**Montaje (los 3 puntos de la incidencia):**
1. `TicketBoard.tsx` `RunModal` — insertar `<ModelEffortPicker variant="block" runtime={agentRuntime} model={agentModel} effort={agentEffort} onChange={...} disabled={isLaunching} />` **dentro del `<div className={styles.modalSection}>` de `:188-202`**, justo después del `<p className={styles.runtimeBadge}>` (`:194-196`).
2. `TicketBoard.tsx` `handleRunConfirm` (`:323-329`) y el resolutor (`:394-402`) — pasar `modelOverride: agentModel` y `effort: agentEffort` a `launchAgentWithRuntime` / `Incidents.runDevResolver`. **Borrar el comentario `:394-396`** que declara que el board no tiene selector (queda falso).
3. `IncidentResolverModal.tsx` (`:408-425`) y `EpicFromBriefModal.tsx` (`:487-514`) — borrar los `<select>` propios y montar `<ModelEffortPicker variant="inline" ... />`. Conservar intacto el envío existente (`IncidentResolverModal.tsx:241-242`, `EpicFromBriefModal` equivalente).

> Si `Incidents.runDevResolver` (`endpoints.ts:4627`) no acepta `effort`, agregarlo como campo opcional del payload y propagarlo en el endpoint correspondiente con la **misma** validación de F2 (`_VALID_EFFORTS` + `_clamp_effort_for_model`). Si ya lo acepta, no tocar.

**Tests (TDD) — `modelEffortModel.test.ts` (vitest, sin DOM):**

| Test | Assert |
|---|---|
| `buildEffortOptions devuelve los 5 efforts siempre` | con Sonnet 5: `length === 5` (KPI-3) |
| `marca xhigh como no soportado en sonnet con su equivalencia` | `find(e => e.id==="xhigh")` → `{supported:false, effective:"high"}` y `note` contiene `"high"` |
| `haiku degrada xhigh y max a high` | ambos `effective === "high"` |
| `opus soporta los 5` | `every(e => e.supported)` |
| `sin modelo elegido no marca nada como no soportado` | `modelId=null` → `every(e => e.supported)` |
| `ninguna opción viene deshabilitada` | el tipo no expone `disabled`; assert de que la lista completa se devuelve para los 4 modelos |
| `buildModelOptions pone el recomendado primero` | `[0].recommended === true` |
| `pickerCapabilities para codex` | `showEfforts === false` y `note` contiene `"--effort"` |
| `pickerCapabilities para catálogo ausente` | `showModels === false`, sin throw |

**Comandos:**
- `npx vitest run src\components\__tests__\modelEffortModel.test.ts`
- `npx vitest run src\store\workbenchPure.test.ts`
- `npx tsc --noEmit`

**Criterio BINARIO:** los 3 comandos verdes **y** el sentinel de unicidad:
`grep -rn "claudeEfforts\|claudeModels" "Stacky Agents/frontend/src"` → **0 matches** (ya no existen listas locales en los modales) y
`grep -rln "ModelEffortPicker" "Stacky Agents/frontend/src"` → **≥ 4 archivos** (definición + 3 montajes).
**Flag que la protege:** `STACKY_MODEL_PICKER_IN_BOARD_ENABLED`, **default ON**.
- Registro: `FlagSpec(key="STACKY_MODEL_PICKER_IN_BOARD_ENABLED", type="bool", label="Selector de modelo/effort en el tablero de tickets", description="Plan 212 — muestra el selector de modelo y effort al lanzar agentes sobre tickets ADO. OFF = el tablero lanza con el default del backend (comportamiento pre-212).", group="global", default=True)` en `backend/services/harness_flags.py` (junto a `STACKY_MODEL_CATALOG_ENABLED`, `:1126-1138`), + entrada en `backend/config.py` con `os.getenv(..., "true")`, + ayuda llana en `backend/services/harness_flags_help.py`.
- **Obligatorio (memoria `harness-flags-default-explicit-gotcha`):** agregar la clave a `_CURATED_DEFAULTS_ON` en `backend/tests/test_harness_flags.py:467`, o `test_default_known_only_for_curated` se pone rojo.
- El frontend la lee vía el gate existente `frontend/src/utils/flagGate.ts` (creado por el Plan 194).
- **Default ON** porque no dispara ninguna de las 4 excepciones duras: no bypasea revisión humana (el operador elige *más* conscientemente), no es destructiva, no requiere prerequisito nuevo (el catálogo ya tiene fallback de emergencia) y no reduce seguridad (la política de modelos sigue en `clamp_model`).
**Impacto por runtime:** los 3 se benefician; el contenido lo dicta el catálogo (Claude: 4 modelos + 5 efforts; Codex: "Automático" + nota; Copilot: modelos vivos, sin efforts). Fallback: catálogo de emergencia completo (F3).
**Trabajo del operador:** ninguno (opt-in con default ON; la preferencia se recuerda).

---

### F5 — Frescura: ver cuán viejo es el catálogo y poder refrescarlo sin F5

**Objetivo (1 frase).** Que "disponibles al momento" sea comprobable: sello de frescura + refresco en 1 click, sin recargar la página.

**Archivos a editar:**
- `Stacky Agents/frontend/src/hooks/useModelCatalog.ts`
- `Stacky Agents/frontend/src/components/ModelEffortPicker.tsx` (creado en F4)

**Cambio — `useModelCatalog` expone `refresh()`, `updatedAt`, `source`:**

```ts
export interface UseModelCatalogResult {
  catalog: Record<string, RuntimeModelCatalog>;
  loading: boolean;
+ /** epoch ms del último fetch exitoso; null si nunca hubo uno */
+ fetchedAt: number | null;
+ /** re-consulta con ?refresh=true e invalida la caché de promesa module-level */
+ refresh: () => Promise<void>;
}
```

Implementación exacta:
1. Mantener `catalogPromise` module-level (no romper el contrato del 159: **un** fetch por sesión en el camino normal).
2. Agregar `let catalogFetchedAt: number | null = null;` module-level, seteado en el `.then`.
3. `refresh()`: `catalogPromise = ModelCatalogApi.get(true);` (el `true` agrega `?refresh=true`, ya soportado — `endpoints.ts:1128-1130` / `api/agents.py:1329`), luego `await` y `setCatalog(resolveModelCatalog(res))`.
4. Suscripción entre instancias: un `Set<() => void>` module-level de listeners; `refresh()` notifica a todas las instancias montadas para que re-lean. Sin librería nueva (riel del 159: `useState` + `useEffect`).

En el picker: una línea al pie — `Catálogo: <source> · actualizado hace <N> min` + botón `↻ Actualizar`. Si `fetchedAt` es null → `Catálogo: fallback de emergencia` en tono de advertencia.

**Tests (TDD) — `Stacky Agents/frontend/src/hooks/__tests__/modelCatalogRefresh.test.ts`:**
- `it("refresh vuelve a pedir el catálogo con refresh=true")` — mock de `ModelCatalogApi.get`, assert de que la 2ª llamada recibió `true`.
- `it("el camino normal hace un solo fetch aunque se monten dos consumidores")` — assert `get` llamado 1 vez (no-regresión del 159).
- `it("refresh notifica a todas las instancias montadas")`.
- Comando: `npx vitest run src\hooks\__tests__\modelCatalogRefresh.test.ts`

**Criterio BINARIO:** comando verde + `npx vitest run src\services\__tests__\modelCatalogFallback.test.ts` verde (no-regresión).
**Flag:** ninguna (mejora estrictamente aditiva sobre un hook existente; sin refrescar, el comportamiento es el del 159).
**Impacto por runtime:** transversal (el endpoint sirve los 3). Refrescar además re-consulta la introspección viva de Copilot (`model_catalog.py:85-105`), que hoy solo se renueva por TTL.
**Trabajo del operador:** ninguno (el botón es opcional).

---

### F6 — Descubrimiento vivo de modelos del CLI, con costo CERO de tokens

**Objetivo (1 frase).** Que el catálogo de Claude Code deje de ser una foto del 2026-07-17 y se complete con lo que el CLI **realmente instalado** declara, sin invocar ningún modelo.

**Archivo a crear:** `Stacky Agents/backend/services/model_probe.py`
**Archivo a editar:** `Stacky Agents/backend/services/model_catalog.py`

**Diseño (explícito y defensivo):**

```python
# services/model_probe.py
from dataclasses import dataclass

# Comandos candidatos de LISTADO, en orden de preferencia. Son de solo lectura:
# ninguno envía un prompt ni consume tokens. Si el subcomando no existe, el CLI
# sale con returncode != 0 y se pasa al siguiente.
_CANDIDATES: tuple[tuple[str, ...], ...] = (
    ("models", "list", "--json"),
    ("models", "--json"),
    ("--list-models",),
)
_TIMEOUT_SEC = 5

@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    models: tuple[str, ...]        # ids descubiertos (puede ser vacío)
    command: str                   # el candidato que funcionó, "" si ninguno
    reason: str                    # "ok" | "cli_not_found" | "no_candidate_worked" | "timeout" | "parse_error"

def probe_claude_models(*, cli_bin: str, timeout_sec: int = _TIMEOUT_SEC) -> ProbeResult:
    """Descubre modelos preguntándole al CLI instalado. NUNCA invoca un modelo.

    Reglas duras:
      - subprocess con timeout, capture_output, sin shell.
      - Se acepta un candidato SOLO si returncode == 0 Y stdout parsea como JSON
        Y de ese JSON se puede extraer una lista de ids no vacía.
      - Cualquier excepción ⇒ ProbeResult(ok=False, ...). Jamás propaga.
    """
```

Extracción de ids del JSON (tolerante, en este orden): `data` si es `list[str]`; `data["models"]` si es lista de str; si es lista de dicts, tomar `m["id"]` o `m["name"]`. Si nada de eso da una lista no vacía → `parse_error`.

**Integración en `load_model_catalog` (union-merge, nunca resta):**
- Nueva función `_merge_probe(catalog: dict) -> dict` llamada al final de `load_model_catalog`, gateada por la flag.
- Regla de merge: para cada id descubierto que **no** esté en `models` del archivo, **agregarlo al final** con `{"id": id, "label": f"{id} (detectado en el CLI)", "recommended": False}`. **Jamás eliminar** un modelo del archivo aunque el probe no lo liste (el probe puede ser incompleto; restar rompería selecciones vigentes).
- `effort_support` para modelos descubiertos: ausente ⇒ el frontend los trata como "soporta todo" (regla 2 de F4) y el backend degrada igual con `_clamp_effort_for_model` (que decide por substring `haiku`/`sonnet`/otro) → **coherente por construcción**.
- Sellar la procedencia: `catalog["runtimes"]["claude_code_cli"]["source"] = "static_config_file+live_probe"` y agregar `"probe": {"ok": ..., "command": ..., "reason": ..., "added": [...]}`.
- Caché: reusar el `_cache` existente (TTL 300s, `model_catalog.py:16,:61-66`). El probe corre **una vez por refresco de caché**, no por request.

**Flag:** `STACKY_MODEL_PROBE_ENABLED`, **default ON**.
- Registro completo igual que en F4 (`harness_flags.py` + `config.py` + `harness_flags_help.py` + `_CURATED_DEFAULTS_ON` en `tests/test_harness_flags.py:467`).
- **Default ON justificado:** costo de tokens **cero** (G6); costo de tiempo acotado a ≤5s **una vez cada 300s** y solo en el path del catálogo; degrada a "solo archivo" ante cualquier problema. No dispara ninguna de las 4 excepciones duras — en particular **no** es "prerequisito no garantizado", porque la ausencia del CLI es un caso previsto que devuelve `cli_not_found` y deja el catálogo intacto.
- Binario del CLI: usar `config.CLAUDE_CODE_CLI_BIN` (ya existe y es configurable desde la UI vía `ClaudeCliConfigModal`).

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan212_model_probe.py`:**

| Test | Assert |
|---|---|
| `test_probe_returns_models_from_first_working_candidate` | fake `subprocess.run` que devuelve JSON válido para el 1er candidato → `ok=True`, ids esperados, `command` == el 1er candidato |
| `test_probe_falls_through_to_second_candidate` | 1er candidato returncode 2, 2º OK → usa el 2º |
| `test_probe_cli_not_found` | `FileNotFoundError` → `ok=False`, `reason=="cli_not_found"`, `models==()` |
| `test_probe_timeout` | `subprocess.TimeoutExpired` → `ok=False`, `reason=="timeout"` |
| `test_probe_bad_json` | stdout `"not json"` en todos → `reason=="no_candidate_worked"` |
| `test_probe_never_raises` | `subprocess.run` lanza `RuntimeError` → devuelve `ProbeResult(ok=False)` sin propagar |
| `test_probe_never_sends_a_prompt` | **guardarraíl G6**: inspecciona los argv capturados y asserta que **ninguno** contiene `-p`, `--print`, `--prompt` ni texto libre; y que todos los argv empiezan con el binario + un candidato de `_CANDIDATES` |
| `test_merge_adds_unknown_models_and_keeps_file_models` | probe devuelve `["claude-sonnet-5", "claude-nuevo-9"]` → catálogo final tiene los 4 del archivo **+** `claude-nuevo-9`, en ese orden |
| `test_merge_never_removes_file_models` | probe devuelve `[]` con `ok=True` → los 4 del archivo siguen |
| `test_flag_off_is_byte_identical` | con `STACKY_MODEL_PROBE_ENABLED=false`, `load_model_catalog()` == el resultado pre-212 y `subprocess.run` **no** se llamó |

**Comando:** `& ".venv\Scripts\python.exe" -m pytest tests\test_plan212_model_probe.py tests\test_plan159_model_catalog_loader.py tests\test_plan159_model_catalog_flag.py -q`
**Criterio BINARIO:** los 3 archivos verdes **y** `grep -rn "subprocess" "Stacky Agents/backend/services/model_probe.py"` → todas las llamadas con `timeout=` y `shell` ausente (revisión manual + el test `test_probe_never_sends_a_prompt`).
**Impacto por runtime:** Claude Code CLI = descubrimiento vivo. Codex CLI = **fuera de scope** (su entrada del catálogo es "Automático" por diseño, `model_catalog.json:34`); documentar la ausencia, no simularla. GitHub Copilot = ya tenía introspección viva (`model_catalog.py:85-105`), no se toca.
**Trabajo del operador:** ninguno.

---

### F7 — "Solicitado vs efectivo": que la degradación se vea, siempre

**Objetivo (1 frase).** Cerrar el bucle de la incidencia: si por cualquier razón el modelo/effort ejecutado difiere del elegido, el operador lo ve (nunca se entera tarde ni nunca).

**Archivos a editar:**
- `Stacky Agents/backend/services/claude_code_cli_runner.py`
- `Stacky Agents/frontend/src/components/ExecutionDetailDrawer.tsx`

**Cambio 1 — persistir el par solicitado/efectivo en la metadata de la ejecución.** En el runner, después de resolver `routed_model` y `_effective_effort` (`claude_code_cli_runner.py:851` y `:879`), escribir en `AgentExecution.metadata_json` la clave:

```python
{
  "model_effort": {
    "requested_model": model_override or config.CLAUDE_CODE_CLI_MODEL or "",
    "effective_model": routed_model or "",
    "requested_effort": effort_override or "",
    "effective_effort": _effective_effort or "",
    "downgraded": bool(
        (model_override and routed_model != model_override)
        or (effort_override and _effective_effort != effort_override)
    ),
    "reason": decision.reason if 'decision' in dir() else "",
  }
}
```

> **Gotcha obligatorio (memoria `plan-209-status`, hallazgo C3):** `AgentExecution.metadata_json` es una columna **`Text`** (`backend/models.py:219`). Escribir un dict directamente la deja como feature muerta silenciosa. Usar el accessor existente `metadata_dict` (`models.py:259`) para leer y **`json.dumps`** para escribir, siguiendo exactamente el patrón que ya usan otros escritores de metadata (leer `harness/post_run.py` y el punto donde se fusiona `metadata_patch` antes de copiarlo).

**Cambio 2 — badge en la UI.** En `ExecutionDetailDrawer.tsx`, si `metadata.model_effort.downgraded === true`, renderizar una línea de advertencia: `Solicitado <requested_model>/<requested_effort> → ejecutado <effective_model>/<effective_effort> — <reason>`. Reusar el estilo de badge existente del drawer; **no** crear un sistema de badges nuevo.

**Tests (TDD):**
- Backend — `Stacky Agents/backend/tests/test_plan212_requested_vs_effective.py`:
  - `test_metadata_records_no_downgrade_when_honored` → `downgraded is False` con Opus elegido (post-F1).
  - `test_metadata_records_downgrade_for_effort` → `effort_override="xhigh"` + Sonnet → `downgraded is True`, `effective_effort == "high"`.
  - `test_metadata_is_valid_json_string` → el valor persistido es `str` y `json.loads` lo parsea (blindaje del gotcha).
  - Comando: `& ".venv\Scripts\python.exe" -m pytest tests\test_plan212_requested_vs_effective.py -q`
- Frontend — extender `modelEffortModel.test.ts` con `describeDowngrade(metadata)` (función pura que arma el string del badge) y sus 3 casos (sin metadata / sin downgrade / con downgrade).

**Criterio BINARIO:** ambos comandos verdes **y** `grep -n "model_effort" "Stacky Agents/backend/services/claude_code_cli_runner.py"` → 1+ match.
**Flag:** ninguna (solo escribe metadata aditiva y renderiza condicionalmente; sin la clave, la UI no muestra nada — degradación natural).
**Impacto por runtime:** Claude Code CLI = completo. Codex CLI = escribe el par con `effective_effort=""` y una `reason` que dice que Codex no usa `--effort` (honestidad, G7). GitHub Copilot = escribe modelo solicitado/efectivo, sin effort.
**Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| Riesgo | Prob. | Mitigación (concreta) |
|---|---|---|
| **Habilitar Opus dispara el costo** de los runs sin que el operador lo note | Media | El desbloqueo requiere elección **explícita por-run** (F1); el default global no desbloquea. El label del catálogo ya advierte *"mayor calidad, más lento, mayor costo"* (`model_catalog.json:11`). El Centro de Costos existente (Plan 142) sigue midiendo por ejecución. |
| **Se rompe el guardarraíl 11** (DevOps nunca Opus) | Baja | El endpoint DevOps clampea con `allow_opus=False`; su `model_override` nunca llega como Opus. Test vivo `test_plan90_devops_agent_endpoints.py:147` se corre en el comando de F1 como no-regresión. |
| **El probe del CLI ejecuta algo inesperado** | Baja | Allowlist cerrada de 3 candidatos de solo-listado, sin `shell`, con timeout 5s, y el test `test_probe_never_sends_a_prompt` inspecciona los argv. Ante cualquier fallo: catálogo del archivo intacto. |
| **El probe agrega modelos basura al selector** | Baja | Union-merge que solo **agrega** ids que el CLI declaró, etiquetados `(detectado en el CLI)` y nunca `recommended`. Si el JSON no parsea, no se agrega nada. |
| **Mostrar efforts no soportados confunde** | Media | No se muestran "pelados": cada uno lleva su equivalencia efectiva (`se aplicará como high`) y la línea `Se ejecutará: …` cierra la duda. Es preferible a la situación actual (opciones ocultas o deshabilitadas sin explicación) y es literalmente lo pedido. |
| **Colisión con Plan 196** (selector en `/planes`) | Media | Contrato declarado arriba: 196 consume `ModelEffortPicker`. Sentinel de F4 (`grep` de listas locales → 0) detecta la duplicación en cualquier orden de implementación. |
| **Rehidratación del store con keys nuevas** | Media | Bump de `WORKBENCH_PERSIST_VERSION` + migración explícita + caso nuevo en `workbenchPure.test.ts` (F4). |
| **Regresión en tests del 159** | Baja | Todos los comandos de F3/F5/F6 incluyen los archivos de test del 159 como no-regresión obligatoria. |
| **Merge duplicado silencioso** al integrar con ramas paralelas (memoria `gotcha-merge-silent-duplicate-keyword`) | Media | Tras cualquier merge: `& ".venv\Scripts\python.exe" -m compileall backend -q`, `npx tsc --noEmit`, y los greps de sentinel de F1/F4/F7. |

---

## 6. Fuera de scope (explícito)

- **Ampliar `_OPUS_ALLOWLIST`** o permitir el tier `fable`. La política de modelos no cambia.
- **Selector de modelo/effort para el agente DevOps** (guardarraíl 11) y para el LLM local (`LocalLlmPlaygroundPanel`, otro dominio).
- **Editor de catálogo desde la UI** (crear/editar modelos a mano). El catálogo se completa solo (F6) o editando el JSON.
- **Introspección viva para Codex CLI** (no expone efforts ni lista de modelos por diseño).
- **Unificar `GET /api/agents/models` y `POST /api/agents/route`** con el catálogo del 159. Están desincronizados (`api/agents.py:1277-1311` sirve `llm_router.CLAUDE_MODELS`, 3 modelos sin Opus), pero su único consumidor es `ModelPicker.tsx`, montado exclusivamente en `InputContextEditor.tsx:94`, marcado como **huérfano** en `TopBar.tsx:29-31`. Tocarlo es deuda separada; este plan no la arrastra. **Se deja anotado como candidato al próximo plan.**
- **Cambiar el selector adaptativo** (`services/adaptive_selector.py`). Sigue actuando solo cuando el operador no eligió.

---

## 7. Glosario

| Término | Significado en Stacky |
|---|---|
| **runtime** | Motor que ejecuta al agente: `claude_code_cli`, `codex_cli`, `github_copilot`. |
| **effort** | Nivel de razonamiento del CLI de Claude (`--effort low\|medium\|high\|xhigh\|max`). Codex no lo soporta como flag. |
| **catálogo de modelos** | Fuente única backend de modelos/efforts por runtime (Plan 159): `config/model_catalog.json` + `services/model_catalog.py` + `GET /api/agents/model-catalog`. |
| **`clamp_model`** | Única función que decide qué modelo está capado (`llm_router.py:38`). Cap duro: Sonnet 5; Opus 4.8 solo con `allow_opus=True`. |
| **`_clamp_effort_for_model`** | Degrada el effort al máximo que soporta el modelo (`api/agents.py:588`). |
| **`model_override` / `effort_override`** | Elección explícita **por-run** que viaja del frontend al runner. |
| **fallback de emergencia** | Catálogo embebido que se usa si el archivo/endpoint falla. Hay uno por lado de la red (`model_catalog.py` y `modelCatalogFallback.ts`). |
| **probe** | Consulta de solo lectura al CLI instalado para descubrir modelos. **No invoca modelos, no gasta tokens.** |
| **ratchet de tests** | `HARNESS_TEST_FILES` en `run_harness_tests.sh`/`.ps1`: lista que solo crece; el meta-test la exige. |
| **`_CURATED_DEFAULTS_ON`** | Set en `tests/test_harness_flags.py:467` donde deben registrarse las flags nuevas con `default=True`. |

---

## 8. Orden de implementación

1. **F0** — tests de caracterización (3 rojos esperados). Registrar en el ratchet.
2. **F1** — `is_opus_allowlisted` + `decide(allow_opus=)` + runner. *(Cierra el bug más grave; independiente del frontend.)*
3. **F2** — canal de effort backend + contratos TS. *(Habilita F4.)*
4. **F3** — catálogo completo + fallbacks + test de paridad. *(Habilita F4 con datos correctos.)*
5. **F4** — `ModelEffortPicker` + montaje en los 3 puntos + store. *(Cierra la incidencia visible.)*
6. **F5** — frescura en el hook + botón. *(Depende de F4 para tener dónde mostrarse.)*
7. **F6** — probe vivo. *(Independiente; puede ir en paralelo a F5.)*
8. **F7** — solicitado vs efectivo. *(Último: consume lo que F1/F2 dejan resuelto.)*

---

## 9. Definición de Hecho (DoD) global

- [ ] `test_plan212_characterization.py` → **6 passed, 0 failed**.
- [ ] Elegir `claude-opus-4-8` en el selector produce `--model claude-opus-4-8` en el comando spawneado (test `test_build_command_receives_opus` verde) — **KPI-1**.
- [ ] `POST /api/agents/run` con `effort` produce `--effort` en el comando; sin `effort` el comportamiento es idéntico al actual — **KPI-2**.
- [ ] El selector del tablero de tickets ADO muestra **todos** los modelos y **los 5 efforts**, con anotación de equivalencia en los degradados — **KPI-3**.
- [ ] `test_plan212_effort_matrix_parity.py` verde; las 3 fuentes de la matriz coinciden — **KPI-4**.
- [ ] El picker muestra la antigüedad del catálogo y `↻ Actualizar` re-consulta sin recargar la página — **KPI-5**.
- [ ] Con `STACKY_MODEL_PICKER_IN_BOARD_ENABLED=false` y `STACKY_MODEL_PROBE_ENABLED=false`, la suite existente pasa sin cambios y el catálogo es byte-idéntico al pre-212 — **KPI-6**.
- [ ] Sentinels: `grep -rn "claudeEfforts\|claudeModels" frontend/src` → **0**; `grep -rln "ModelEffortPicker" frontend/src` → **≥4**; `grep -n "allow_opus" backend/services/claude_code_cli_runner.py` → **≥2**.
- [ ] Las 2 flags nuevas están en `harness_flags.py` + `config.py` + `harness_flags_help.py` + `_CURATED_DEFAULTS_ON`, y son editables desde la UI de flags (riel: config del operador siempre por UI).
- [ ] Los 5 archivos de test nuevos están en `run_harness_tests.sh` **y** `run_harness_tests.ps1`; `test_harness_ratchet_meta.py` verde.
- [ ] `& ".venv\Scripts\python.exe" -m compileall backend -q` sin errores y `npx tsc --noEmit` limpio.
- [ ] Paridad de runtimes verificada ítem por ítem (tabla de cada fase), con el fallback de cada uno documentado.
- [ ] Trabajo del operador: **ninguno** en todas las fases (opt-in con default ON donde aplica; ninguna de las 4 excepciones duras se dispara).
