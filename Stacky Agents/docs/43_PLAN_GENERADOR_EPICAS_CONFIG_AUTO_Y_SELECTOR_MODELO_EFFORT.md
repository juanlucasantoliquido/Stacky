# Plan 43 — Generador de Épicas: Config Auto-Silenciosa + Selector Modelo/Effort Completo

**Versión:** v2 — 2026-06-18
**Estado:** IMPLEMENTADO 2026-06-19 (F0–F4). Backend: `llm_router.clamp_model(allow_opus)` + `_OPUS_ALLOWLIST={"claude-opus-4-8"}` (llm_router.py:32-51), `_clamp_effort_for_model` + whitelist {low,medium,high,xhigh,max} + `allow_opus=True` en run_brief (agents.py:544-609). Frontend: `CLAUDE_MODELS` (sonnet-4-6/opus-4-8/haiku-4-5), `CLAUDE_EFFORTS` 5 niveles + `isEffortValidForModel`, probe auto al montar y selectores (EpicFromBriefModal.tsx:24-47,96-170,436-456), `endpoints.ts` effort ampliado (endpoints.ts:994). Verde: test_llm_router_opus_flag.py, test_run_brief_efforts.py, test_run_brief_model_override.py; tsc --noEmit exit 0. (Header "PROPUESTO" original era stale.)
**Autor:** StackyArchitectaUltraEficientCode

### Changelog
- **v2 (2026-06-18):** Decisión del operador: Opus 4.8 debe estar SIEMPRE visible y usable en el selector del generador de épicas, sin flag ni paso de configuración extra. Cambios respecto a v1:
  - ELIMINADO por completo el flag `STACKY_EPIC_ALLOW_OPUS` y toda lógica de gating/allowlist condicional por entorno.
  - `clamp_model` ahora acepta un parámetro `allow_opus: bool = False` (default conserva el cap global intacto para todos los demás flujos). El flujo brief→épica llama SIEMPRE con `allow_opus=True` de forma determinística (NO env var apagable).
  - `_OPUS_ALLOWLIST = {"claude-opus-4-8"}` se conserva como control explícito por id (fable y otros Opus siguen capados).
  - Se conserva la NOTA de costo (Opus $5/$25 vs Sonnet $3/$15) como advertencia informativa en UI/`.env.example`, sin gating.
  - Tests de F1 reescritos: ya no testean el env flag; testean `allow_opus=True/False` y que `run_brief` pasa siempre `allow_opus=True`.
- **v1 (2026-06-18):** Versión inicial con flag `STACKY_EPIC_ALLOW_OPUS` (descartada).

---

## 1. Objetivo

Cerrar dos incidencias del modal "Épica desde Brief":

**Incidencia 1 (I1) — Config manual obligatoria:** Al abrir el generador con runtime `claude_code_cli`, si Claude Code no está logueado, el modal obliga al operador a abrir manualmente el panel de configuración, esperar, y hacer clic en "Listo". Debe ser automático y silencioso: probe al montar, preparar si es posible, nunca abrir el modal de config sin que el operador lo pida.

**Incidencia 2 (I2) — Selector incompleto:** (a) `CLAUDE_MODELS` en `EpicFromBriefModal.tsx:22-25` incluye `claude-haiku-3-5` (id inválido; el correcto es `claude-haiku-4-5`) y omite Opus 4.8. (b) El selector de effort solo expone `high/medium/low` con etiquetas en español; faltan `xhigh` y `max`, que son los valores oficiales del CLI de Claude para tareas agenticas complejas.

**KPI de éxito:**
- 0 clics manuales de configuración en el flujo normal (I1).
- CLAUDE_MODELS contiene exactamente `claude-sonnet-4-6` (default), `claude-opus-4-8` y opcionalmente `claude-haiku-4-5` (id correcto); ningún id inválido (I2a).
- El selector de effort muestra las 5 opciones oficiales: `low`, `medium`, `high`, `xhigh`, `max`, con `high` como default; efforts inválidos para el modelo elegido quedan deshabilitados (I2b).
- Opus 4.8 es seleccionable Y usable end-to-end SIN flag ni configuración extra: elegir Opus en el modal → backend pasa `model_override=claude-opus-4-8` al runner (no clampado).
- 0 regresiones en tests existentes de `clamp_model` y del cap global (el cap sigue activo para todo flujo que NO sea brief→épica).

---

## 2. Por qué ahora / Gap que cierra

El plan 42 resolvió el wiring `model_override` + `effort_override` en `run_brief` (backend `agents.py:554-571` + `agents.py:621-622` + runner `claude_code_cli_runner.py:1681-1689`). Los datos YA fluyen desde el frontend al runner. Lo que falta es:

| Gap | Evidencia |
|-----|-----------|
| `probeClaude()` nunca se llama al montar el modal; solo al cambiar runtime | `EpicFromBriefModal.tsx:87-99` — sin `useEffect` de mount |
| Si no está listo, `handleRuntimeChange` ABRE el modal de config automáticamente | `EpicFromBriefModal.tsx:101-111` — comportamiento intrusivo |
| `CLAUDE_MODELS` tiene `claude-haiku-3-5` (id inválido) y no tiene Opus 4.8 | `EpicFromBriefModal.tsx:22-25` |
| `clamp_model` bloquea Opus con cap duro y el flujo brief→épica no puede levantarlo | `llm_router.py:33-45` — `_FORBIDDEN_CLAUDE_TIER = ("opus","fable")`, firma `clamp_model(model)` sin parámetro de excepción |
| Backend solo acepta `low/medium/high` en `effort_override` | `agents.py:570-571` |
| Runner solo pasa `--effort` para `low/medium/high`; ignora `xhigh`/`max` | `claude_code_cli_runner.py:1687-1688` |
| Tipo TypeScript de `effort` es `"low"\|"medium"\|"high"` | `EpicFromBriefModal.tsx:72` |

---

## 3. Principios y guardarraíles

1. **Paridad de 3 runtimes con fallback explícito.** Los selectores de modelo y effort aplican plenamente solo a `claude_code_cli`. Para `codex` y `github_copilot` el selector se oculta/deshabilita; el backend ignora `model_override` y usa el effort más conservador soportado.
2. **Cero trabajo extra al operador.** La preparación de sesión es silenciosa. El operador no hace nada en el flujo normal.
3. **Human-in-the-loop innegociable.** El modal sigue requiriendo que el operador revise el brief y apruebe la generación.
4. **Cap global intacto fuera de brief→épica.** El default de `clamp_model` (`allow_opus=False`) mantiene el cap duro idéntico al actual para todo el sistema. El flujo brief→épica es el ÚNICO que llama con `allow_opus=True`, y lo hace SIEMPRE de forma determinística (sin env var, sin paso de configuración): Opus 4.8 es de primera clase en ese flujo. No hay flag apagable.
5. **No degradar.** 0 regresiones en los test files existentes.
6. **Backward-compatible.** `run_brief` sigue aceptando llamadas sin `model`/`effort` en el body; los defaults son `sonnet-4-6` y `high`.
7. **Reusar lo existente.** No crear nuevos servicios; ampliar los existentes con cambios mínimos localizados.

---

## 4. Fases

### F0 — Backend: ampliar set de efforts aceptados

**Objetivo:** que `agents.py` y `claude_code_cli_runner.py` acepten y pasen `xhigh`/`max` además de `low/medium/high`.

**Archivos afectados:**
- `Stacky Agents/backend/api/agents.py` líneas 570-571
- `Stacky Agents/backend/services/claude_code_cli_runner.py` líneas 1687-1688

**Cambio en `agents.py:570-571`** — ampliar whitelist de effort:

```python
# ANTES (línea 570-571):
_VALID_EFFORTS = {"low", "medium", "high"}
effort_override = _effort_raw if _effort_raw in _VALID_EFFORTS else "high"

# DESPUÉS:
_VALID_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
effort_override = _effort_raw if _effort_raw in _VALID_EFFORTS else "high"
```

**Cambio en `claude_code_cli_runner.py:1687-1688`** — ampliar whitelist del runner:

```python
# ANTES (línea 1687-1688):
if effort in ("low", "medium", "high"):
    cmd.extend(["--effort", effort])

# DESPUÉS:
_RUNNER_VALID_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
if effort in _RUNNER_VALID_EFFORTS:
    cmd.extend(["--effort", effort])
```

**Clamp seguro por modelo (en `agents.py`, después de calcular `effort_override`):**

Agregar la función de clamp `_clamp_effort_for_model(effort, model_id)` como función privada en `agents.py`, justo antes del bloque que calcula `effort_override`:

```python
def _clamp_effort_for_model(effort: str, model_id: str | None) -> str:
    """
    Degrada effort al máximo soportado por el modelo.
    Matriz modelo x effort (oficial Claude CLI):
      claude-haiku-*   : soporta solo low/medium/high  → xhigh→high, max→high
      claude-sonnet-*  : soporta low/medium/high/max   → xhigh→high (xhigh es Opus 4.7+)
      claude-opus-4-5+ : soporta low/medium/high/xhigh/max
      claude-opus-4-8  : soporta todo
    """
    if not model_id:
        return effort
    m = model_id.lower()
    if "haiku" in m:
        return effort if effort in ("low", "medium", "high") else "high"
    if "sonnet" in m:
        # sonnet no soporta xhigh (es Opus 4.7+); max sí en sonnet-4-6
        return "high" if effort == "xhigh" else effort
    # opus: todo soportado
    return effort
```

Llamar al final de la lógica de `effort_override`, antes de pasar al runner:

```python
effort_override = _clamp_effort_for_model(effort_override, model_override)
```

**Tests — archivo:** `Stacky Agents/backend/tests/test_run_brief_efforts.py` (nuevo)

Casos obligatorios:
1. `effort=xhigh` → `effort_override="xhigh"` (pasa whitelist).
2. `effort=max` → `effort_override="max"` (pasa whitelist).
3. `effort=invalid` → `effort_override="high"` (default).
4. `_clamp_effort_for_model("xhigh", "claude-sonnet-4-6")` → `"high"`.
5. `_clamp_effort_for_model("max", "claude-sonnet-4-6")` → `"max"`.
6. `_clamp_effort_for_model("xhigh", "claude-haiku-4-5")` → `"high"`.
7. `_clamp_effort_for_model("xhigh", "claude-opus-4-8")` → `"xhigh"`.
8. `_clamp_effort_for_model("max", "claude-opus-4-8")` → `"max"`.

**Comando de test:**
```
"N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents/backend/tests/test_run_brief_efforts.py" -v
```

**Criterio de aceptación:** 8/8 verde, 0 regresiones en `test_run_brief_model_override.py`.

**Flag de protección:** ninguno necesario (ampliar set de valores válidos es backward-compatible; el default sigue siendo `high`).

**Impacto por runtime:**
- `claude_code_cli`: recibe `--effort xhigh` o `--effort max` cuando el modelo lo soporta.
- `codex`: `effort_override` se calcula pero el runner de Codex no usa `--effort`; se ignora silenciosamente.
- `github_copilot`: ídem Codex.

**Trabajo del operador:** ninguno.

---

### F1 — Backend: Opus 4.8 de primera clase en brief→épica (sin flag)

**Objetivo:** que `clamp_model` no bloquee `claude-opus-4-8` cuando el operador lo selecciona en el flujo brief→épica, SIN flag ni configuración extra, manteniendo el cap global intacto para el resto del sistema. Opus es seleccionable y usable SIEMPRE en este flujo; Sonnet 4.6 sigue siendo el default seleccionado.

**Archivos afectados:**
- `Stacky Agents/backend/services/llm_router.py` líneas 24-45
- `Stacky Agents/backend/api/agents.py` línea 568

**Problema de diseño — tensión de política (resuelta sin flag):**

El cap duro `_FORBIDDEN_CLAUDE_TIER = ("opus","fable")` en `llm_router.py:43-44` existe para evitar costos inesperados de Opus en el harness general (Opus 4.8 = USD 5/MTok input, USD 25/MTok output vs Sonnet 4.6 = USD 3/MTok, USD 15/MTok). No se levanta ese cap globalmente. La solución más pequeña y segura es un parámetro explícito de la función, NO una env var: `clamp_model(model, allow_opus=False)`. El flujo brief→épica (`run_brief`) llama SIEMPRE con `allow_opus=True` de forma determinística (codificado, no apagable). Todo otro caller usa el default `False` y conserva el cap. Así Opus es de primera clase en épicas sin riesgo de costo en el resto del sistema y sin que el operador tenga que configurar nada.

**Cambio en `llm_router.py`:**

```python
# ANTES (líneas 33-45):
CLAUDE_CAP_MODEL = "claude-sonnet-4-6"
_FORBIDDEN_CLAUDE_TIER = ("opus", "fable")

def clamp_model(model: str | None) -> str:
    if not model:
        return CLAUDE_CAP_MODEL
    low = model.lower()
    if low.startswith("claude-") and any(t in low for t in _FORBIDDEN_CLAUDE_TIER):
        return CLAUDE_CAP_MODEL
    return model

# DESPUÉS:
CLAUDE_CAP_MODEL = "claude-sonnet-4-6"
_FORBIDDEN_CLAUDE_TIER = ("opus", "fable")
_OPUS_ALLOWLIST = {"claude-opus-4-8"}  # Opus explícitamente permitido cuando allow_opus=True

def clamp_model(model: str | None, allow_opus: bool = False) -> str:
    """Aplica el cap duro de §5.2 sobre un id de modelo Claude.

    allow_opus=True (lo usa SOLO el flujo brief→épica) exime de clamp a los
    modelos en _OPUS_ALLOWLIST. fable y cualquier Opus fuera de la allowlist
    siguen capados aun con allow_opus=True. El default (False) preserva el cap
    global para todos los demás callers.
    """
    if not model:
        return CLAUDE_CAP_MODEL
    low = model.lower()
    if low.startswith("claude-") and any(t in low for t in _FORBIDDEN_CLAUDE_TIER):
        if allow_opus and model in _OPUS_ALLOWLIST:
            return model
        return CLAUDE_CAP_MODEL
    return model
```

**Cambio en `agents.py:568`** — pasar `allow_opus=True` SIEMPRE (sin condición, sin env):

```python
# ANTES (línea 568):
model_override = _llm_router.clamp_model(_requested_model) if _requested_model else None

# DESPUÉS:
# brief→épica permite Opus 4.8 de primera clase, siempre (decisión del operador, sin flag).
model_override = _llm_router.clamp_model(_requested_model, allow_opus=True) if _requested_model else None
```

No se agrega ninguna variable a `config.py` ni a `.env.example`. NO existe `STACKY_EPIC_ALLOW_OPUS`.

**Nota de costo (informativa, sin gating):** la advertencia de costo de Opus ($5/$25 vs Sonnet $3/$15) vive en la etiqueta del selector (F3, `CLAUDE_MODELS`: "Opus 4.8 (mayor calidad, más lento, mayor costo)") y se documenta en el riesgo correspondiente. No bloquea nada.

**Tests — archivo:** `Stacky Agents/backend/tests/test_llm_router_opus_flag.py` (nuevo)

Casos obligatorios:
1. `clamp_model("claude-opus-4-8", allow_opus=False)` → `"claude-sonnet-4-6"` (cap intacto por default).
2. `clamp_model("claude-opus-4-8", allow_opus=True)` → `"claude-opus-4-8"` (permitido en allowlist).
3. `clamp_model("claude-opus-4-8")` (sin segundo arg) → `"claude-sonnet-4-6"` (default `False`, backward-compatible con callers existentes).
4. `clamp_model("claude-sonnet-4-6", allow_opus=True)` → `"claude-sonnet-4-6"` (no toca sonnet).
5. `clamp_model("claude-haiku-4-5", allow_opus=True)` → `"claude-haiku-4-5"` (no toca haiku).
6. `clamp_model("claude-fable-5", allow_opus=True)` → `"claude-sonnet-4-6"` (fable sigue bloqueado; `_OPUS_ALLOWLIST` no incluye fable).
7. `clamp_model("claude-opus-4-7", allow_opus=True)` → `"claude-sonnet-4-6"` (Opus 4.7 no está en `_OPUS_ALLOWLIST`; solo 4.8 está permitido explícitamente).
8. `clamp_model("", allow_opus=True)` → `"claude-sonnet-4-6"` (default sin cambios).
9. Llamada a `run_brief` con `model=claude-opus-4-8` → `model_override="claude-opus-4-8"` (el flujo pasa `allow_opus=True` SIEMPRE; sin depender de ninguna env var).

**Comando de test:**
```
"N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents/backend/tests/test_llm_router_opus_flag.py" -v
```

**Criterio de aceptación:** 9/9 verde; tests existentes de `clamp_model` sin regresión (correr también `test_run_brief_model_override.py`). El default `allow_opus=False` garantiza que todo caller existente que llama `clamp_model(model)` con un solo argumento mantiene su comportamiento.

**Flag de protección:** ninguno. Es una decisión de política determinística codificada en el call site de `run_brief`. El default de la función (`False`) protege al resto del sistema.

**Impacto por runtime:**
- `claude_code_cli`: el operador elige Opus 4.8 y el runner recibe `--model claude-opus-4-8` (sin paso previo).
- `codex` / `github_copilot`: `model_override` se calcula pero esos runners no usan `--model`; se ignora.

**Trabajo del operador:** ninguno. Opus aparece y funciona directamente.

---

### F2 — Frontend: auto-config silenciosa al abrir el modal

**Objetivo:** que `probeClaude()` se dispare automáticamente al montar el modal (o al cambiar a `claude_code_cli`) sin abrir el panel de configuración. El botón "Configurar" queda como respaldo opcional.

**Archivo afectado:**
`Stacky Agents/frontend/src/components/EpicFromBriefModal.tsx`

**Cambios exactos:**

**2a. Agregar `useEffect` de mount** (después de la declaración de estados, alrededor de línea 85):

```typescript
// Nuevo: disparar probe silencioso al montar o al cambiar a claude_code_cli
useEffect(() => {
  if (agentRuntime === "claude_code_cli") {
    void probeClaude();
  }
}, [agentRuntime]);
```

`probeClaude` ya es `async` y hace `setClaudeChecking(true/false)` + `setClaudeSession(...)`. No requiere cambios internos.

**2b. Cambiar `handleRuntimeChange` (líneas 101-111)** — eliminar la apertura automática del modal:

```typescript
// ANTES (línea 101-111):
async function handleRuntimeChange(rt: string) {
  setAgentRuntime(rt);
  if (rt === "claude_code_cli") {
    await probeClaude();
    if (!claudeReady) {
      setShowClaudeConfig(true);  // ← ELIMINAR esta línea
    }
  }
}

// DESPUÉS:
async function handleRuntimeChange(rt: string) {
  setAgentRuntime(rt);
  // probeClaude se dispara via useEffect([agentRuntime]); no abrir config automáticamente
}
```

Nota: con el `useEffect` de 2a, el probe ya ocurrirá reactivamente al cambiar `agentRuntime`. `handleRuntimeChange` puede simplificarse a solo `setAgentRuntime(rt)`.

**2c. Cambiar el bloque de warning (líneas 290-307)** — reemplazar el bloque "no configurado + modal automático" por un aviso no intrusivo:

```typescript
// ANTES (línea 290-307): bloque que muestra banner de error + botón Configurar

// DESPUÉS: aviso inline NO bloqueante
{agentRuntime === "claude_code_cli" && claudeChecking && (
  <div className="text-xs text-gray-400 mt-1">Verificando sesión Claude Code...</div>
)}
{agentRuntime === "claude_code_cli" && !claudeChecking && !claudeReady && (
  <div className="text-xs text-yellow-600 mt-1 flex items-center gap-2">
    <span>Claude Code no está listo.</span>
    <button
      type="button"
      className="underline text-yellow-700"
      onClick={() => setShowClaudeConfig(true)}
    >
      Configurar
    </button>
  </div>
)}
{agentRuntime === "claude_code_cli" && !claudeChecking && claudeReady && (
  <div className="text-xs text-green-600 mt-1">Claude Code listo.</div>
)}
```

**2d. `canGenerate` (línea 263-264):** sin cambio. Sigue bloqueando si `claude_code_cli && !claudeReady`. El operador solo puede generar cuando el probe confirma que Claude está listo.

**Criterio de aceptación:** `tsc` sin errores en `frontend/src`; build de producción (`npm run build`) sin errores.

**Comando de validación:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend" && npx tsc --noEmit
```

**Flag de protección:** ninguno (comportamiento de UI mejorado, no es cambio de política).

**Impacto por runtime:**
- `claude_code_cli`: probe automático al montar.
- `codex` / `github_copilot`: `agentRuntime !== "claude_code_cli"` → el `useEffect` no dispara probe; no hay cambio de comportamiento.

**Trabajo del operador:** ninguno en el flujo normal.

---

### F3 — Frontend: selector de modelo y effort completos

**Objetivo:** corregir `CLAUDE_MODELS`, agregar Opus 4.8, completar el selector de effort con los 5 valores oficiales, deshabilitar efforts no válidos según el modelo.

**Archivo afectado:**
`Stacky Agents/frontend/src/components/EpicFromBriefModal.tsx`

**3a. Corregir `CLAUDE_MODELS` (líneas 22-25):**

```typescript
// ANTES (línea 22-25):
const CLAUDE_MODELS: { value: string; label: string }[] = [
  { value: "claude-sonnet-4-6", label: "Sonnet 4.6 (recomendado)" },
  { value: "claude-haiku-3-5", label: "Haiku 3.5 (más rápido)" },  // id inválido
];

// DESPUÉS:
const CLAUDE_MODELS: { value: string; label: string }[] = [
  { value: "claude-sonnet-4-6", label: "Sonnet 4.6 (recomendado)" },
  { value: "claude-opus-4-8", label: "Opus 4.8 (mayor calidad, más lento, mayor costo)" },
  { value: "claude-haiku-4-5", label: "Haiku 4.5 (más rápido, menor costo)" },
];
```

El default `useState<string>("claude-sonnet-4-6")` en línea 71 no cambia.

**3b. Tipo de effort (línea 72):**

```typescript
// ANTES:
const [selectedEffort, setSelectedEffort] = useState<"low"|"medium"|"high">("high");

// DESPUÉS:
type EffortLevel = "low" | "medium" | "high" | "xhigh" | "max";
const [selectedEffort, setSelectedEffort] = useState<EffortLevel>("high");
```

**3c. Definir constante `CLAUDE_EFFORTS` con la matriz modelo×effort** (agregar junto a `CLAUDE_MODELS`, línea ~26):

```typescript
// Efforts oficiales de Claude CLI
// Matriz soporte: haiku → low/medium/high; sonnet → low/medium/high/max; opus → todos
const CLAUDE_EFFORTS: {
  value: EffortLevel;
  label: string;
  supportedModels: string[];  // prefijos de modelo que soportan este effort
}[] = [
  {
    value: "low",
    label: "low — mínimo (respuestas rápidas)",
    supportedModels: ["claude-haiku", "claude-sonnet", "claude-opus"],
  },
  {
    value: "medium",
    label: "medium — estándar",
    supportedModels: ["claude-haiku", "claude-sonnet", "claude-opus"],
  },
  {
    value: "high",
    label: "high — alto (recomendado para épicas)",
    supportedModels: ["claude-haiku", "claude-sonnet", "claude-opus"],
  },
  {
    value: "xhigh",
    label: "xhigh — muy alto (Opus 4.7+)",
    supportedModels: ["claude-opus"],
  },
  {
    value: "max",
    label: "max — máximo (Opus 4.8 / Sonnet 4.6)",
    supportedModels: ["claude-sonnet", "claude-opus"],
  },
];

// Helper: ¿es el effort válido para el modelo seleccionado?
function isEffortValidForModel(effort: EffortLevel, modelId: string): boolean {
  const entry = CLAUDE_EFFORTS.find((e) => e.value === effort);
  if (!entry) return false;
  return entry.supportedModels.some((prefix) => modelId.startsWith(prefix));
}
```

**3d. Agregar efecto de guard: si el modelo cambia y el effort actual no es válido, resetear a "high"** (después de los `useState`, línea ~85):

```typescript
useEffect(() => {
  if (!isEffortValidForModel(selectedEffort, selectedModel)) {
    setSelectedEffort("high");
  }
}, [selectedModel]);
```

**3e. Actualizar el selector de effort en el JSX (líneas 309-335):**

```tsx
// ANTES: 3 <option> hardcodeadas (alto/medio/bajo)

// DESPUÉS: mapear CLAUDE_EFFORTS, deshabilitar los no válidos para el modelo
<select
  value={selectedEffort}
  onChange={(e) => setSelectedEffort(e.target.value as EffortLevel)}
  disabled={agentRuntime !== "claude_code_cli"}
  className="..."
>
  {CLAUDE_EFFORTS.map((e) => {
    const valid = isEffortValidForModel(e.value, selectedModel);
    return (
      <option key={e.value} value={e.value} disabled={!valid}>
        {e.label}{!valid ? " (no disponible para este modelo)" : ""}
      </option>
    );
  })}
</select>
```

**3f. `handleGenerate` (línea 190-196):** sin cambio estructural; `selectedEffort` ya se envía como `effort` en `runBrief`. Solo verificar que el tipo actualizado `EffortLevel` no rompa la firma de `Agents.runBrief`.

**Criterio de aceptación:** `tsc --noEmit` sin errores; los 3 modelos y los 5 efforts aparecen en el selector; `xhigh` y `max` deshabilitados cuando el modelo es Haiku; `xhigh` deshabilitado cuando el modelo es Sonnet.

**Comando de validación:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend" && npx tsc --noEmit
```

**Flag de protección:** ninguno. El selector de Opus tiene efecto directo: el backend (F1) pasa `allow_opus=True` siempre en brief→épica, así que `claude-opus-4-8` no se clampea. El operador ve la opción y funciona de inmediato.

**Impacto por runtime:**
- `claude_code_cli`: los selectores están habilitados; effort y modelo se envían.
- `codex` / `github_copilot`: selectores deshabilitados (`disabled={agentRuntime !== "claude_code_cli"}`); no se envían o se ignoran en backend.

**Trabajo del operador:** ninguno.

---

### F4 — Frontend: actualizar tipos en `endpoints.ts`

**Objetivo:** alinear el tipo de `effort` en la firma de `Agents.runBrief` con el set ampliado.

**Archivo afectado:**
`Stacky Agents/frontend/src/api/endpoints.ts`

**Cambio:** buscar la interfaz o tipo que define el payload de `runBrief`. Si tiene `effort?: "low" | "medium" | "high"`, ampliar a:

```typescript
effort?: "low" | "medium" | "high" | "xhigh" | "max";
```

Si el tipo está inline en la función, extraerlo o ampliar la unión en el mismo lugar. Si ya es `string`, no hay cambio necesario.

**Criterio de aceptación:** `tsc --noEmit` sin errores después de aplicar F3.

**Comando de validación:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend" && npx tsc --noEmit
```

**Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| Riesgo | Probabilidad | Mitigación |
|--------|-------------|------------|
| CLI `claude` no acepta `--effort xhigh` o `--effort max` (depende de versión instalada) | Media | El runner en `claude_code_cli_runner.py` puede capturar el stderr de spawn; si aparece "unknown option --effort", loguear warning y reintentar sin `--effort`. A corto plazo, el operador verá el run fallado con mensaje claro. En F0 documentar que la versión mínima del CLI de Claude requerida para xhigh/max debe verificarse. |
| Costo de Opus 4.8 si el operador lo elige sin entender el tradeoff | Media (Opus visible y usable siempre) | Mitigación informativa (NO gating, por decisión del operador): la etiqueta del selector marca "mayor costo"; Sonnet 4.6 sigue siendo el default seleccionado, así que el camino por defecto es el barato. El operador asume el costo conscientemente al cambiar a Opus. |
| `isEffortValidForModel` incorrecta (falso-positivo que permite xhigh en Sonnet) | Baja | Los tests de F0 `_clamp_effort_for_model` son el backstop backend; incluso si el frontend envía xhigh para Sonnet, el backend clampea a high. Doble guardia. |
| Probe automático de sesión Claude al montar el modal genera una llamada de red extra en cada apertura | Baja | `probeClaude()` llama `ClaudeCli.session()` que es un GET liviano. Aceptable. Cacheable en el futuro si es necesario. |
| `clamp_model` con `allow_opus=True` acepta Opus 4.7 u otro Opus si alguien lo escribe en el body manualmente | Controlada | `_OPUS_ALLOWLIST = {"claude-opus-4-8"}` hace el control explícito por id. Cualquier otro id de Opus sigue siendo bloqueado aun con `allow_opus=True`. |
| Otro flujo del sistema empieza a usar Opus por la nueva firma | Muy baja | Solo `run_brief` pasa `allow_opus=True`; el default `False` mantiene el cap para todos los demás callers. Revisar en code review que ningún otro call site agregue `allow_opus=True`. |
| Regresión en tests existentes de `clamp_model` por la nueva firma `allow_opus=False` | Muy baja | El parámetro tiene default `False`; todos los tests existentes que llaman `clamp_model(model)` sin el segundo argumento siguen funcionando. |

---

## 6. Fuera de scope

- Auto-login de Claude Code (la probe solo verifica el estado; el login interactivo es del operador).
- Exposición de Opus 4.8 en el harness general (solo en brief→épica, vía `allow_opus=True` en ese único call site).
- Soporte de `--effort` para runtimes Codex o GitHub Copilot Pro.
- Cambios en el agente `BusinessAgent.agent.md`.
- Agregar `claude-haiku-4-5` al harness general (`llm_router.CLAUDE_MODELS`); queda solo en el selector del modal.

---

## 7. Glosario

| Término | Definición |
|---------|-----------|
| `clamp_model` | Función en `llm_router.py` que baja cualquier modelo prohibido al cap `claude-sonnet-4-6`. |
| `effort` | Parámetro de `output_config` del CLI de Claude que controla la profundidad de razonamiento. Valores: `low`, `medium`, `high`, `xhigh`, `max`. |
| `xhigh` | Effort entre `high` y `max`; soportado en Opus 4.7+ (incluyendo 4.8). Default de Claude Code para tareas agenticas complejas. |
| `max` | Effort máximo; soportado en Opus 4.6+, Sonnet 4.6, Fable 5. No disponible en Haiku ni Sonnet 4.5. |
| `allow_opus` | Parámetro de `clamp_model` (bool, default `False`). Solo el flujo `run_brief` / brief→épica lo pasa en `True`, de forma determinística y sin env var, para habilitar Opus 4.8. |
| `probeClaude()` | Función en `EpicFromBriefModal.tsx` que llama `ClaudeCli.session()` y actualiza el estado `claudeSession`. |
| `_OPUS_ALLOWLIST` | Set de ids de modelos Opus permitidos cuando `allow_opus=True`. Inicialmente `{"claude-opus-4-8"}`. |
| `_clamp_effort_for_model` | Función privada en `agents.py` que degrada un effort al máximo soportado por el modelo dado. |

---

## 8. Orden de implementación y DoD global

### Orden de implementación

1. **F0** — Ampliar whitelist de efforts en backend (no tiene dependencias).
2. **F1** — Modificar `clamp_model` (agregar parámetro `allow_opus`) y pasar `allow_opus=True` desde `run_brief` (no tiene dependencias de F0, pero F0 y F1 pueden hacerse en la misma sesión). Sin flag ni cambios en `config.py`/`.env.example`.
3. **F4** — Actualizar tipos en `endpoints.ts` (hacerlo antes de F3 para que tsc valide F3).
4. **F2** — Auto-config silenciosa en frontend (requiere que F1 esté verde para no bloquear la generación con Opus).
5. **F3** — Selector de modelo y effort completos (requiere F1 para que Opus no sea clampado y F4 para los tipos).

### DoD global (Definition of Done)

- [ ] `test_run_brief_efforts.py`: 8/8 verde.
- [ ] `test_llm_router_opus_flag.py`: 9/9 verde.
- [ ] `test_run_brief_model_override.py`: sin regresiones (todos verdes).
- [ ] `npx tsc --noEmit` en `frontend/`: 0 errores.
- [ ] `npm run build` en `frontend/`: 0 errores.
- [ ] NO existe ninguna referencia a `STACKY_EPIC_ALLOW_OPUS` en el repo (grep vacío); no se agregó nada a `config.py` ni `.env.example`.
- [ ] `clamp_model("claude-opus-4-8")` sin segundo arg → `claude-sonnet-4-6` (cap global intacto para el resto del sistema).
- [ ] Seleccionar Opus en el modal (sin configurar nada) → backend envía `model_override=claude-opus-4-8` al runner.
- [ ] Al abrir el modal con runtime `claude_code_cli`: probe automático sin abrir panel de configuración.
- [ ] Selector de effort muestra 5 opciones; `xhigh`/`max` deshabilitados para Haiku; `xhigh` deshabilitado para Sonnet 4.6.
- [ ] `effort=xhigh` y `effort=max` llegan al runner sin ser descartados (cuando modelo los soporta).
