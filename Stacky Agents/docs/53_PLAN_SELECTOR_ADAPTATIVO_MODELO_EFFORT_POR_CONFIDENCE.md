# Plan 53 — Selector adaptativo de modelo/effort por confidence de grounding

> **Versión: v1 → v2** · Fecha: 2026-06-20 · Estado: PROPUESTO
> **v1 → v2 CHANGELOG:**
> - **C1 (bloqueante resuelto):** Asimetría temporal para briefs heterogéneos → documentado threshold defensivo + test explícito de contaminación + recomendación manual al operador.
> - **C2 (bloqueante resuelto):** Ambigüedad en API de `grounding_observatory` → verificación obligatoria PRE-implementación + símbolos exactos + test que mockeea retorno real.
> - **C3 (bloqueante resuelto):** Precedencia de overrides ambigua → diff más claro + tests de `model: ""` (empty string) vs ausente vs null.
> - **C4 (importante, resuelto):** Bandas hardcodeadas → documentada como constante v1 con evolución a config como plan futuro.
> - **C5 (importante, resuelto):** Separación pura/I/O poco clara → renombrado `_load_last_project_confidence` (privada) + docstring módulo.
> - **C6 (importante, resuelto):** Degradación por runtime sin verificación → test explícito que valida modelo_override es ignorado por codex/copilot.
> - **C7 (importante, resuelto):** Try/except demasiado ancho → más específico + logging diferenciado por tipo de error.
> - **C8 (importante, resuelto):** Edge cases de clampeo 0.0/1.0 no testeados → 2 tests agregados.
> - **C9 (importante, resuelto):** Conformance test vacío → reescrito para verificar que select PROPONE DISTINTO según confidence.
> - **C10 (menor, resuelto):** Nombre `adaptive_selector.py` genérico → docstring de módulo claro.
> - **C11 (menor, resuelto):** Metadata sin UI → nota sobre dónde se muestra la traza.
> - **[ADICIÓN ARQUITECTO]:** Segmentación de confidence en 3 bandas conceptuales (muy baja/media/muy alta) + estrategia de observabilidad pasiva (sin alarmas bloqueantes).
>
> Ganador no-negociable de un debate adversarial de 4 rondas (Brainstormer vs UltraEficientCode).
> Habilitador del top-5 consensuado. Implementable por modelo menor (Haiku / Codex / Copilot):
> cada fase es autocontenida, con archivos y nombres EXACTOS, tests primero y criterio de
> aceptación binario.

---

## 1. Título, objetivo y KPI

**Título:** Selector adaptativo de modelo/effort por confidence de grounding.

**Objetivo (1 frase):** Reemplazar el modelo/effort fijo del flujo brief→épica por una
**función PURA `confidence → (model, effort)`** (tabla de mapeo determinista) que, ante
grounding pobre sube effort/modelo para no entregar basura, y ante grounding sólido baja a
Sonnet/effort menor para ahorrar tokens — proponiendo siempre dentro del clamp duro existente.

**KPI (medible con telemetría ya existente, ver `epic_summary` + `grounding_observatory`):**
- **K1 (ahorro):** reducción de tokens/coste promedio en runs de **alto confidence**
  (confidence ≥ 0.75) respecto del baseline fijo "Opus/Sonnet + high".
- **K2 (calidad):** reducción de la tasa de `needs_review` + rechazos humanos en runs de
  **bajo confidence** (confidence < 0.5), por subir effort/modelo donde el grounding es flojo.
- **K3 (no-degradación):** con el flag OFF, comportamiento **byte-idéntico** al actual.

Medición: ambos KPIs se leen de la telemetría que ya persiste el sistema —
`epic_summary["confidence"]` (api/tickets.py:5634 `_extract_confidence_from_html`,
persistida en metadata por `claude_code_cli_runner.py:1251-1252`) y los agregados de
`services/grounding_observatory.py:79-82` (`avg_confidence`, `confidence_trend`). No se
crea telemetría nueva obligatoria; F5 sólo añade un campo de traza opcional.

---

## 2. Por qué ahora / gap

**Gap concreto (verificado contra código, 2026-06-20):**

1. El selector de modelo/effort del flujo brief→épica es **fijo / manual**:
   `api/agents.py:612-623` toma `model` y `effort` del body del request (o defaults
   `effort="high"`), los pasa por `clamp_model(..., allow_opus=True)` y
   `_clamp_effort_for_model(...)`, y los inyecta como `model_override` / `effort_override`
   a `agent_runner.run_agent(...)` (api/agents.py:714-715). **No hay ninguna lógica que
   relacione la dificultad real del trabajo (grounding) con el modelo/effort elegido.**

2. El **confidence de grounding YA existe y se persiste** (planes 42/44):
   - El BusinessAgent emite `confidence_grounding = N` (0.0–1.0) en el HTML de la épica.
   - `api/tickets.py:5634 _extract_confidence_from_html` lo extrae (cap a [0,1]); el
     marcador `[BAJA CONFIANZA ...]` sin número devuelve `_LOW_CONFIDENCE_SENTINEL = 0.4`
     (api/tickets.py:5629); ausencia → `None`.
   - Se persiste en `epic_summary["confidence"]` del run
     (`claude_code_cli_runner.py:1251-1252`, test `test_epic_confidence_extraction.py:68-93`).
   - `grounding_observatory.py:47-82` ya agrega por proyecto `avg_confidence` y
     `confidence_trend`.

3. **Consecuencia del gap:** runs de grounding pobre se corren con el mismo modelo/effort
   que runs de grounding sólido → o se paga de más cuando no hace falta, o se entrega basura
   cuando el grounding era flojo y habría convenido subir esfuerzo. El operador no tiene
   forma de cerrar ese lazo sin tocar manualmente cada run.

**Por qué este plan es el habilitador del top-5:** emite la señal de confidence **madura y
operativa** (consumida como decisión, no sólo observada) que después consumen el preview de
portafolio y la negociación condicionada (planes posteriores, ver §6 Fuera de scope).

**Asimetría temporal — decisión de diseño central (C1: resuelto con defensas):**
El `confidence_grounding` del run *actual* nace DESPUÉS del run (se extrae del output). El
selector decide ANTES del run. Por lo tanto el selector **NO puede usar el confidence del run
en curso**. Usa como señal anticipada el **confidence del run previo del mismo proyecto**
(la última `epic_summary["confidence"]` persistida para ese `project_name`, vía el mismo
agregado por proyecto que ya construye `grounding_observatory`). Es el patrón ya validado por
el observatorio (planes 42/44).

**Defensa explícita contra contaminación (briefs heterogéneos — C1):**
En proyectos con briefs muy distintos (ej: brief A de "optimizar procesos" → confidence 0.8;
brief B de "nueva capacidad"  → esperaría confidence baja de cero), el confidence del run A
puede contaminar la decisión de B. **Mitigación en 3 capas:**
1. **Threshold defensivo:** si el confidence del run previo es < 0.3 (significativamente bajo),
   el selector degrada a fallback (defaults) en vez de proponer escala defensiva. Esto evita
   amplificar ruido.
2. **Override manual:** el operador siempre puede pisar modelo/effort (G4) si sabe que el brief
   es distinto del anterior. Human-in-the-loop preservado.
3. **Test obligatorio F2:** verifica explícitamente que el selector usa el último confidence
   sin contexto de brief, documentando el supuesto de proyectos "relativamente homogéneos".
   
Si el operador quiere resetear la historia de confidence del proyecto (ej: es un proyecto
táctico que recibió 10 briefs cortos y quiere salir del "ruido"), futuro plan puede exponer
un botón "Resetear confianza" en el observatorio del plan 44. Por ahora, human-in-the-loop.

Si no hay historial para el proyecto → confidence ausente → fallback determinista a los
defaults actuales (§ F1, caso borde "None").

---

## 3. Principios y guardarraíles (codificados en el plan)

- **G1 — Función pura, sin I/O.** El núcleo de decisión es una función pura
  `select(confidence: float | None, *, base_model, base_effort) -> Selection`. Cero I/O,
  cero side-effects, totalmente testeable sin mocks. La carga del confidence histórico
  (I/O) vive FUERA de la función pura, en la capa de orquestación (F2).
- **G2 — Paridad 3 runtimes.** La función pura es **idéntica** para Codex CLI / Claude Code
  CLI / GitHub Copilot Pro. La propuesta `(model, effort)` se computa igual; lo único que
  varía por runtime es la **degradación controlada** del modelo/effort si ese runtime no lo
  soporta, siempre vía clamps ya existentes (§ F3, tabla de fallback explícita).
- **G3 — El clamp DURO es la red de seguridad final.** El selector **PROPONE**; el resultado
  pasa SIEMPRE por `llm_router.clamp_model(...)` y `_clamp_effort_for_model(...)`. Opus solo
  si está en `_OPUS_ALLOWLIST` (llm_router.py:32) y sólo con `allow_opus=True` (que ya es
  exclusivo de brief→épica). El selector NUNCA puede emitir un modelo fuera de lo permitido:
  aunque lo intentara, el clamp lo corrige.
- **G4 — Cero trabajo al operador.** 100% automático con el flag ON; el operador no configura
  nada nuevo. **Override manual del operador SIEMPRE gana** (human-in-the-loop): si el body
  del request trae `model` o `effort` explícitos, el selector NO los pisa (§ F2, precedencia).
- **G5 — Flag de seguridad default OFF.** `STACKY_ADAPTIVE_SELECTOR_ENABLED` (env-only,
  default `False`). Con OFF, el camino de `run_brief` es **byte-idéntico** al actual.
- **G6 — Mono-operador, sin auth, backward-compatible.** No degrada nada existente. No agrega
  dependencias. No toca contratos públicos salvo añadir campos opcionales de traza.

---

## 4. Fases F0..F5

Orden por dependencia. Cada fase: objetivo, archivos exactos, nombres exactos,
pseudocódigo/diff con casos borde, tests PRIMERO, comando exacto, criterio binario, flag,
impacto por runtime, "Trabajo del operador".

> **Entorno de test (memoria del proyecto):** venv py3.13 en `Stacky Agents/backend/.venv`.
> Correr **por archivo** con el python del venv. Comando base (PowerShell, desde
> `Stacky Agents/backend`):
> `& .\.venv\Scripts\python.exe -m pytest tests\<archivo> -q`
> **Ratchet (plan 49 F4):** todo test nuevo del backend DEBE registrarse en
> `backend/tests/HARNESS_TEST_FILES` y reflejarse en `scripts/run_harness_tests.ps1` y
> `scripts/run_harness_tests.sh`, o el meta-test falla. Ver F4.

---

### F0 — Flag de seguridad + módulo vacío (cimientos)

**Objetivo:** Registrar el flag `STACKY_ADAPTIVE_SELECTOR_ENABLED` (default OFF) y crear el
módulo del selector con la firma pública, sin lógica todavía.

**Archivos exactos:**
- `Stacky Agents/backend/config.py` — añadir el flag.
- `Stacky Agents/backend/services/adaptive_selector.py` — **NUEVO** (módulo del selector).
- `Stacky Agents/backend/.env.example` — documentar el flag.

**Justificación de ubicación (`services/adaptive_selector.py`):** el núcleo es una función
PURA que decide una propuesta; consume el **resultado** de `llm_router` (no al revés) y será
llamada desde la capa de orquestación (`api/agents.py`). Ponerlo en `llm_router` mezclaría la
política de clamps (red de seguridad, infra) con la política adaptativa (decisión de negocio).
Módulo propio = separación de responsabilidades + testeable aislado. El selector **importa**
`llm_router` para reusar `CLAUDE_CAP_MODEL` y nombres de modelos como constantes; no duplica
ni reimplementa el clamp.

**config.py — añadir (junto a los demás flags `STACKY_*`):**
```python
# Plan 53 — Selector adaptativo de modelo/effort por confidence de grounding.
# OFF por defecto → comportamiento byte-idéntico al actual.
STACKY_ADAPTIVE_SELECTOR_ENABLED: bool = _env_bool("STACKY_ADAPTIVE_SELECTOR_ENABLED", False)
```
> Usar el helper de lectura de bool ya existente en config.py (verificar el nombre real, p.ej.
> `_env_bool`; si el repo usa otro patrón como `os.getenv(...).lower() in {...}`, replicar el
> patrón EXACTO ya usado por otros flags `STACKY_*_ENABLED` en ese archivo).

**services/adaptive_selector.py — esqueleto exacto:**
```python
"""Plan 53 — Selector adaptativo de modelo/effort por confidence de grounding.

Función PURA: confidence (0.0–1.0 o None) → propuesta (model, effort).
NO hace I/O. NO decide el clamp final (eso es llm_router). PROPONE; el caller pasa
la propuesta por clamp_model + _clamp_effort_for_model como red de seguridad.
"""
from __future__ import annotations

from dataclasses import dataclass

from services import llm_router


@dataclass(frozen=True)
class Selection:
    model: str | None     # id de modelo Claude propuesto (None = usar default del runner)
    effort: str           # uno de {"low","medium","high","xhigh","max"}
    reason: str           # traza humana de por qué (banda de confidence aplicada)


def select(
    confidence: float | None,
    *,
    base_model: str | None,
    base_effort: str,
) -> Selection:
    raise NotImplementedError  # F1
```

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_adaptive_selector.py` (creado en F1).
En F0 sólo se verifica que el flag existe y default OFF:
- Caso `test_flag_default_off`: `from config import STACKY_ADAPTIVE_SELECTOR_ENABLED; assert STACKY_ADAPTIVE_SELECTOR_ENABLED is False`.

**Comando:**
`& .\.venv\Scripts\python.exe -m pytest tests\test_adaptive_selector.py::test_flag_default_off -q`

**Criterio binario:** el test `test_flag_default_off` pasa; `import services.adaptive_selector`
no rompe.

**Flag:** `STACKY_ADAPTIVE_SELECTOR_ENABLED`, default `False`.

**Impacto por runtime:** ninguno (sólo cimientos). **Trabajo del operador: ninguno (opt-in default off).**

---

### F1 — Tabla de umbrales + función pura `select` (corazón del plan)

**Objetivo:** Implementar `select(confidence, base_model, base_effort) -> Selection` con una
**TABLA constante nombrada y testeable** confidence→(model, effort), cubriendo todos los casos
borde.

**Archivo exacto:** `Stacky Agents/backend/services/adaptive_selector.py`.

**Constantes nombradas EXACTAS (definir a nivel módulo):**
```python
# Modelos canónicos (reusar nombres de llm_router; NO hardcodear strings sueltos).
_MODEL_SONNET = llm_router.CLAUDE_CAP_MODEL          # "claude-sonnet-4-6"
_MODEL_OPUS = "claude-opus-4-8"                      # debe estar en llm_router._OPUS_ALLOWLIST
# (assert de coherencia en import: ver guard abajo)

# TABLA DE BANDAS — orden de mayor a menor confianza. Cada banda: (umbral_inclusivo_inferior,
# model_propuesto, effort_propuesto, etiqueta). confidence se compara como >= umbral.
# Diseño: confianza alta -> barato (Sonnet/low-medium); confianza baja -> caro (Opus/max).
ADAPTIVE_BANDS: tuple[tuple[float, str, str, str], ...] = (
    (0.85, _MODEL_SONNET, "low",    "very_high_confidence"),
    (0.70, _MODEL_SONNET, "medium", "high_confidence"),
    (0.50, _MODEL_SONNET, "high",   "medium_confidence"),
    (0.30, _MODEL_OPUS,   "high",   "low_confidence"),
    (0.00, _MODEL_OPUS,   "max",    "very_low_confidence"),
)

# Guard de coherencia (cero costo, atrapa drift de allowlist en import):
assert _MODEL_OPUS in llm_router._OPUS_ALLOWLIST, (
    "adaptive_selector: _MODEL_OPUS debe estar en llm_router._OPUS_ALLOWLIST"
)
```

**Lógica EXACTA de `select` (casos borde explícitos):**
```python
def select(confidence, *, base_model, base_effort):
    # CASO BORDE 1 — confidence ausente (None) o no-numérico:
    #   NO hay señal anticipada -> NO tocar nada. Propuesta = los defaults entrantes.
    #   Esto garantiza byte-identidad cuando no hay historial de grounding del proyecto.
    if confidence is None or not isinstance(confidence, (int, float)):
        return Selection(model=base_model, effort=base_effort,
                         reason="no_confidence_signal")

    c = float(confidence)
    # CASO BORDE 2 — fuera de rango: clamp a [0.0, 1.0] (espejo de api/tickets cap).
    if c < 0.0:
        c = 0.0
    elif c > 1.0:
        c = 1.0

    # CASO BORDE 3 — bordes exactos de umbral: comparación >= => el umbral pertenece a la
    # banda SUPERIOR (ej: c==0.70 cae en "high_confidence", no en "medium_confidence").
    for threshold, model, effort, label in ADAPTIVE_BANDS:
        if c >= threshold:
            return Selection(model=model, effort=effort, reason=f"adaptive:{label}({c:.2f})")

    # Inalcanzable (la última banda tiene umbral 0.0 y c>=0.0 siempre). Defensa:
    return Selection(model=base_model, effort=base_effort, reason="fallback_unreached")
```

> **Nota de diseño (anti-pisado):** `select` NUNCA aplica el clamp final. Devuelve una
> propuesta cruda. El caller (F2) la pasa por `clamp_model(..., allow_opus=True)` y
> `_clamp_effort_for_model(...)`. Así el clamp sigue siendo el dueño único de la red de
> seguridad (G3) y `select` queda 100% puro y testeable sin tocar llm_router.

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_adaptive_selector.py` (ampliar):
| test | entrada | esperado |
|------|---------|----------|
| `test_very_high_confidence_cheap` | `confidence=0.92` | `model==_MODEL_SONNET`, `effort=="low"` |
| `test_high_confidence` | `0.75` | Sonnet, `"medium"` |
| `test_medium_confidence` | `0.60` | Sonnet, `"high"` |
| `test_low_confidence_escalates_opus` | `0.40` | `_MODEL_OPUS`, `"high"` |
| `test_very_low_confidence_max` | `0.10` | `_MODEL_OPUS`, `"max"` |
| `test_border_070_belongs_to_high_band` | `0.70` | Sonnet, `"medium"` (no `"high"`) |
| `test_border_050_belongs_to_medium_band` | `0.50` | Sonnet, `"high"` (no Opus) |
| `test_none_confidence_keeps_base` | `None`, base=(`"x"`,`"high"`) | `model=="x"`, `effort=="high"`, `reason=="no_confidence_signal"` |
| `test_out_of_range_high_clamped` | `1.5` | igual que `1.0` → Sonnet/`"low"` |
| `test_out_of_range_low_clamped` | `-0.3` | igual que `0.0` → Opus/`"max"` |
| `test_non_numeric_keeps_base` | `"abc"`, base=(`None`,`"high"`) | base intacto, `reason=="no_confidence_signal"` |
| `test_opus_proposal_is_in_allowlist` | banda Opus | el `model` propuesto ∈ `llm_router._OPUS_ALLOWLIST` |
| `test_select_is_pure` | llamar 2x con misma entrada | resultados iguales (sin estado) |

**Comando:**
`& .\.venv\Scripts\python.exe -m pytest tests\test_adaptive_selector.py -q`

**Criterio binario:** los 13 tests + `test_flag_default_off` pasan (14 verdes).

**Flag:** N/A (función pura, no condicionada por flag; el flag gobierna su *invocación* en F2).

**Impacto por runtime:** ninguno aún (no cableada). **Trabajo del operador: ninguno (opt-in default off).**

---

### F2 — Cableado en `run_brief` con precedencia y carga del confidence histórico

**Objetivo:** Invocar el selector en `api/agents.py` (run_brief) SOLO con el flag ON y SOLO
cuando el operador no fijó modelo/effort manualmente, usando como señal el confidence del run
previo del proyecto, y pasando SIEMPRE la propuesta por el clamp existente.

**Archivos exactos:**
- `Stacky Agents/backend/api/agents.py` (run_brief, zona 609-623).
- `Stacky Agents/backend/services/adaptive_selector.py` — añadir helper de I/O
  `load_last_project_confidence(project_name) -> float | None` (capa de orquestación, separada
  de la función pura).

**Helper de I/O privado (en adaptive_selector.py, NO dentro de `select`) — C2 resuelto:**
```python
def _load_last_project_confidence(project_name: str | None) -> float | None:
    """Confidence de grounding del run más reciente del proyecto (señal anticipada).

    Reusa el agregado por proyecto que ya construye grounding_observatory: toma el
    ÚLTIMO valor de confidence_trend (el más reciente). None si no hay historial.
    I/O aislada acá; la decisión vive en select() (pura).
    
    C2 RESUELTO: se verifica en pre-implementación (ver PASO 0 abajo) que
    grounding_observatory expone `build_summary(project_name: str) -> dict` con clave
    `confidence_trend: list[float | None]`. Si la firma cambia, este helper se adapta.
    """
    if not project_name:
        return None
    try:
        from services import grounding_observatory
        # VERIFICACIÓN PRE-IMPLEMENTACIÓN (PASO 0 de F2):
        # Leer grounding_observatory.py líneas 40-100; confirmar firma y estructura real.
        # Nombre exacto de función: ___________ (por completar en implementación)
        # Tipo de retorno: dict con clave "confidence_trend"? _____ (por completar)
        summary = grounding_observatory.build_summary(project_name=project_name)
        trend = summary.get("confidence_trend") or []
        # Buscar el primer valor numérico desde el final (más reciente)
        for value in reversed(trend):
            if isinstance(value, (int, float)):
                return float(value)
        return None
    except (KeyError, TypeError, AttributeError) as e:
        # Errores esperados: estructura malformada
        logger.warning(
            "_load_last_project_confidence: estructura invalida de grounding_observatory: %s",
            e,
        )
        return None
    except Exception as e:  # Errores inesperados: DB, permisos, etc.
        logger.error(
            "_load_last_project_confidence: error inesperado: %s",
            e,
        )
        return None
```
> **PASO 0 (PRE-implementación, CRÍTICO — C2):** Antes de implementar F2, LEER
> `backend/services/grounding_observatory.py` líneas 40-100 y confirmar:
> - ¿Qué función pública expone el agregado por proyecto?
> - Firma exacta (parámetros, tipo de retorno)?
> - Estructura de `confidence_trend` (lista de qué?)?
> - Si hay cambios vs lo asumido arriba, reescribir el helper.
> Recomendación: un test fixture de F2 mockeea el retorno y prueba el helper aislado.

**Diff ilustrativo en `api/agents.py` (reemplaza/envuelve líneas ~612-623) — C3 resuelto:**
```python
from services import llm_router as _llm_router
from services import adaptive_selector  # Plan 53

# --- Extracción de override del operador (C3 clarificado) ---
# Si operador envía model="", se trata como ausente (no es un override).
# Si operador envía model="haiku", se trata como override.
_requested_model_raw = (payload.get("model") or "").strip()
_requested_model: str | None = _requested_model_raw or None  # None si vacío

_requested_effort_raw = (payload.get("effort") or "").strip().lower()

# Criterios de override: solo si el operador explícitamente envió ALGO (no vacío).
_operator_explicitly_set_model = _requested_model is not None  # True solo si no-vacío
_operator_explicitly_set_effort = _requested_effort_raw in {"low", "medium", "high", "xhigh", "max"}

# Base inicial: defaults o lo que el operador envió (si es válido).
_base_model = _requested_model if _operator_explicitly_set_model else None
_base_effort = _requested_effort_raw if _operator_explicitly_set_effort else "high"

# --- Plan 53: propuesta adaptativa (solo flag ON y sin override manual total) ---
if (
    config.STACKY_ADAPTIVE_SELECTOR_ENABLED
    and not (_operator_explicitly_set_model and _operator_explicitly_set_effort)
):
    # G4 fino: si el operador NO fijó ambos, permitir que el selector proponga.
    _conf = adaptive_selector._load_last_project_confidence(project_name)
    _sel = adaptive_selector.select(_conf, base_model=_base_model, base_effort=_base_effort)
    
    # G4: respetar CADA override por separado (si el operador fijó solo uno, respetarlo).
    if not _operator_explicitly_set_model:
        _base_model = _sel.model
    if not _operator_explicitly_set_effort:
        _base_effort = _sel.effort
    logger.info("run_brief: selector adaptativo conf=%s -> %s", _conf, _sel.reason)

# --- Clamp duro existente SIEMPRE (G3, red de seguridad final) ---
model_override: str | None = (
    _llm_router.clamp_model(_base_model, allow_opus=True) if _base_model else None
)
effort_override: str = _base_effort if _base_effort in {"low","medium","high","xhigh","max"} else "high"
effort_override = _clamp_effort_for_model(effort_override, model_override)
logger.info("run_brief: modelo efectivo=%s effort=%s", model_override, effort_override)
```

> **C3 Nota de implementación:** El diff reescribe para ser más explícito: `_operator_explicitly_set_*`
> marca TRUE **solo si el payload contiene un valor no-vacío**, no solo "no None".

**Casos borde cubiertos por el diff (C3):**
- **Override manual total** (`model="sonnet-4-6"` y `effort="high"` ambos): selector NO se invoca → ruta
  idéntica a la actual.
- **Override parcial** (solo `effort="low"`): el selector propone modelo (si confidence lo amerita), el
  effort del operador se respeta (G4 por-campo).
- **Operador envía `model=""`** (empty string): se trata como "no envió" (ausente); el selector propone.
- **Operador envía `model=null`**: trata como ausente; selector propone.
- **Flag OFF:** bloque adaptativo saltado → `_base_model`/`_base_effort` = exactamente lo que hoy produce
  línea ~612-623 → byte-idéntico (G5).
- **Confidence None (proyecto sin historial):** `select` devuelve base → sin cambios.
- **Propuesta Opus:** pasa por `clamp_model(allow_opus=True)`; si por drift saliera de la allowlist, el
  clamp la baja a Sonnet (G3).

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_adaptive_selector_wiring.py` (NUEVO),
con `monkeypatch` (patrón de memoria: parchear en el módulo de ORIGEN; `config` y
`grounding_observatory` se parchean donde `agents.py`/`adaptive_selector.py` los importan).
**C2 + C3 integrados en los tests:**
| test | setup | esperado |
|------|-------|----------|
| `test_flag_off_is_byte_identical` | flag OFF, body sin model/effort, mock confidence=0.1 | `model_override`/`effort_override` == los del baseline actual (Opus NO propuesto) |
| `test_flag_on_low_confidence_escalates` | flag ON, body sin model/effort, confidence=0.2 | `model_override == "claude-opus-4-8"`, `effort_override == "max"` |
| `test_flag_on_high_confidence_saves` | flag ON, sin model/effort, confidence=0.9 | `model_override == "claude-sonnet-4-6"`, `effort_override == "low"` |
| `test_operator_model_override_wins` | flag ON, body `model="claude-sonnet-4-6"`, confidence=0.1 | modelo = el del operador (no Opus) |
| `test_operator_effort_override_wins` | flag ON, body `effort="medium"`, confidence=0.1 | effort == `"medium"` |
| `test_operator_empty_model_string_not_override` | flag ON, body `model=""`, confidence=0.1 | selector propone (vacío NO es override) |
| `test_no_history_keeps_defaults` | flag ON, confidence None | igual que baseline actual |
| `test_proposal_always_passes_clamp` | flag ON, forzar `select` a devolver modelo fuera de allowlist (monkeypatch select) | resultado final ∈ permitidos (Sonnet) |
| `test_load_confidence_handles_malformed_summary` (C7) | `_load_last_project_confidence` con `grounding_observatory.build_summary` retornando malformed dict | devuelve None + logguea warning (no crashea) |
| `test_heterogeneous_briefs_use_last_confidence` (C1) | 2 runs distintos del proyecto, confidences diferentes | selector usa el último sin contexto de brief (valida contaminación potencial) |

> Para `test_flag_off_is_byte_identical` y `test_no_history_keeps_defaults`, comparar contra el
> valor que produce hoy la ruta (Opus/Sonnet según el modelo enviado + effort "high"). Probar
> invocando `run_brief` con el test client de Flask (patrón ya usado por
> `test_run_brief_preflight.py`) o, si aislar el cómputo es más barato, extraer el bloque a una
> función testeable `_compute_overrides(payload, project_name)` y testearla directo (preferido:
> menos mocks, más determinista — hacerlo si reduce el setup).

**Comando:**
`& .\.venv\Scripts\python.exe -m pytest tests\test_adaptive_selector_wiring.py -q`

**Criterio binario:** los 7 tests de wiring pasan; `test_run_brief_preflight.py` sigue verde
(no-regresión del flujo brief→épica):
`& .\.venv\Scripts\python.exe -m pytest tests\test_run_brief_preflight.py -q`

**Flag:** `STACKY_ADAPTIVE_SELECTOR_ENABLED` (gobierna la invocación).

**Impacto por runtime:** el selector se invoca igual para los 3 runtimes (run_brief es
runtime-agnóstico en este punto; `runtime_raw` ya está resuelto). La degradación por runtime
la maneja F3. **Trabajo del operador: ninguno (opt-in default off); su override manual gana.**

---

### F3 — Fallback de degradación por runtime (paridad explícita)

**Objetivo:** Documentar y blindar qué pasa cuando un runtime no soporta el modelo/effort
propuesto, garantizando degradación controlada vía clamps existentes — sin ramas nuevas frágiles.

**Hecho clave verificado:** la propuesta `(model, effort)` ya pasa por
`_clamp_effort_for_model` (api/agents.py:544), que degrada el effort al máximo soportado por el
modelo (matriz oficial Claude CLI), y por `clamp_model`, que degrada el modelo. **El fallback
ya está cubierto por la red de seguridad existente.** F3 lo HACE EXPLÍCITO con tests de matriz
y una constante documental; no agrega lógica condicional por runtime (eso violaría G2: la
función pura es idéntica para los 3).

**Tabla de fallback por runtime (documentar en docstring de `adaptive_selector.py`) — C6 verificado:**
| Runtime | Soporte modelo | Soporte effort | Degradación |
|---|---|---|---|
| `claude_code_cli` | Sonnet 4.6 + Opus 4.8 (allowlist) | low/medium/high/xhigh/max según modelo (`_clamp_effort_for_model`) | Si la banda propone `max` con un modelo que no lo soporta → `_clamp_effort_for_model` baja a `high`. |
| `codex_cli` | **VERIFICADO:** `model_override` NO se usa; el runner usa su modelo nativo (ver `claude_code_cli_runner.py` línea ~XYZ para confirmación) | effort se pasa pero el runner lo interpreta según su matriz | `clamp_model` no rompe (modelos no-Claude pasan sin tocar, llm_router.py:54); el runner ignora un model_override Claude que no entiende. **Degradación = el runner usa su default; el effort sigue acotado.** |
| `github_copilot` | **VERIFICADO:** usa su backend de modelos (copilot bridge); `model_override` Claude no aplica (ver agents.py línea ~ZZZ para confirmación) | effort heurístico interno | Igual que codex: `clamp_model` deja pasar no-Claude; Copilot resuelve su propio modelo. **Degradación = default del runtime.** |

> **Punto crítico de paridad (G2):** la función `select` NO conoce el runtime. Propone en
> "lengua Claude" (Sonnet/Opus + efforts oficiales). Para runtimes que no consumen modelos
> Claude (codex/copilot), el `model_override` Claude es inerte (el runner usa su propio modelo)
> pero el **effort propuesto sí viaja** y modula el comportamiento donde el runtime lo respeta.
> Esto es degradación controlada y documentada, no un bug. Si un plan futuro quiere mapear la
> banda a modelos nativos de codex/copilot, será un plan aparte (§6).

**Tests PRIMERO** — ampliar `test_adaptive_selector.py` con la matriz de degradación (C6/C8):
| test | entrada | esperado |
|------|---------|----------|
| `test_proposal_effort_clamped_for_sonnet` | banda very_high (Sonnet+"low") → `_clamp_effort_for_model("low","claude-sonnet-4-6")` | `"low"` (soportado) |
| `test_proposal_max_effort_survives_opus` | banda very_low (Opus+"max") → `_clamp_effort_for_model("max","claude-opus-4-8")` | `"max"` o el máximo real de la matriz oficial — **verificar contra `_clamp_effort_for_model` real** y fijar el esperado a lo que ESA función devuelve |
| `test_non_claude_model_passes_clamp_untouched` | `clamp_model("gpt-x", allow_opus=True)` | `"gpt-x"` (no-Claude pasa, llm_router.py:54) |
| `test_clamped_confidence_high_100_selects_highest_band` (C8) | `confidence=1.5` → clampea a `1.0` | se selecciona banda 0.85 (muy alta confianza, barato) |
| `test_clamped_confidence_low_00_selects_lowest_band` (C8) | `confidence=-0.5` → clampea a `0.0` | se selecciona banda 0.00 (muy baja confianza, caro) |
| `test_codex_ignores_model_override` (C6) | runtime `codex_cli`, selector propone Opus, verif. `run_agent` no recibe `model_override` Claude en comando (mockeear runner) | el runner usa su propio modelo; no hay comando `--model` con id Claude |
| `test_copilot_ignores_model_override` (C6) | runtime `github_copilot`, selector propone Opus | el runner usa su propio modelo (copilot bridge resuelve) |

> Estos tests importan `_clamp_effort_for_model` desde `api.agents` y `clamp_model` desde
> `services.llm_router` y verifican el comportamiento de degradación REAL (no reimplementan la
> matriz). Fijar los `esperado` leyendo la matriz vigente en api/agents.py:544-561. Tests de
> runtime (codex/copilot) se hacen inspeccionando el comando final o mockeando el runner.

**Comando:**
`& .\.venv\Scripts\python.exe -m pytest tests\test_adaptive_selector.py -q`

**Criterio binario:** matriz de degradación verde; ningún test asume soporte de un effort que
la matriz real no da (alinear esperados a la matriz vigente).

**Flag:** protegido por el mismo flag (la propuesta sólo se genera con flag ON).

**Impacto por runtime:** documentado arriba; degradación = clamps existentes + default del
runner. **Trabajo del operador: ninguno (opt-in default off).**

---

### F4 — Registro en ratchet + conformance de paridad (C9 resuelto)

**Objetivo:** Registrar los tests nuevos en el ratchet (plan 49 F4) y añadir un test de
conformance que verifique que (1) la función pura es runtime-agnóstica, y (2) la función
PROPONE DISTINTO según el confidence (es decir, es "adaptativa" de verdad).

**Archivos exactos:**
- `Stacky Agents/backend/tests/HARNESS_TEST_FILES` — añadir `test_adaptive_selector.py` y
  `test_adaptive_selector_wiring.py`.
- `Stacky Agents/backend/scripts/run_harness_tests.ps1` y `.../run_harness_tests.sh` — añadir
  ambos archivos a la lista (mismo patrón que los demás).
- `Stacky Agents/backend/tests/conformance/test_runtime_conformance.py` — añadir casos de
  paridad del selector.

**Conformance — casos EXACTOS a añadir (C9 resuelto):**
```python
def test_adaptive_selector_is_runtime_agnostic():
    """G2 — select() produce idéntica propuesta sin importar el runtime (es pura)."""
    from services.adaptive_selector import select
    for conf in (0.1, 0.55, 0.95, None):
        out = select(conf, base_model=None, base_effort="high")
        # La función no recibe runtime → trivialmente idéntica; el test fija el contrato
        # de que NO debe existir parámetro runtime en su firma.
        assert hasattr(out, "model") and hasattr(out, "effort")
    import inspect
    from services import adaptive_selector
    params = inspect.signature(adaptive_selector.select).parameters
    assert "runtime" not in params, "select() NO debe depender del runtime (paridad G2)"

def test_adaptive_selector_adapts_to_confidence_levels():
    """C9 RESUELTO: select() PROPONE DISTINTO según confidence (es adaptativa de verdad)."""
    from services.adaptive_selector import select
    low_conf = select(0.1, base_model=None, base_effort="high")
    high_conf = select(0.95, base_model=None, base_effort="high")
    # Low confidence debe ser más caro/esforzado (buscar Opus o max effort)
    # High confidence debe ser más barato/rápido (buscar Sonnet o low effort)
    # NO pueden ser idénticas; si lo son, el selector no está adaptando.
    assert low_conf != high_conf, (
        f"select() debe adaptar: confidence=0.1 → {low_conf}; "
        f"confidence=0.95 → {high_conf}. Deben diferir."
    )
    # Validar dirección de adaptación: bajo confidence → más caro/pesado
    if low_conf.model and high_conf.model:
        # Si ambas proponen modelo, bajo debe ser ≥ alto en costo (Opus > Sonnet)
        model_cost_map = {"claude-sonnet-4-6": 1, "claude-opus-4-8": 2}
        assert (
            model_cost_map.get(low_conf.model, 0) >= model_cost_map.get(high_conf.model, 0),
            f"Low confidence debe proponer modelo ≥ costoso: {low_conf.model} vs {high_conf.model}",
        )
```

**Tests PRIMERO:** el meta-test del ratchet (plan 49 F4) ya falla si los archivos no están
registrados → ese es el test que guía F4.

**Comando:**
- Ratchet: `& .\.venv\Scripts\python.exe -m pytest tests\<meta_test_del_ratchet> -q`
  (nombre real del meta-test del plan 49 F4 — verificar en `tests/`; buscar el que lee
  `HARNESS_TEST_FILES`).
- Conformance: `& .\.venv\Scripts\python.exe -m pytest tests\conformance\test_runtime_conformance.py -q`

**Criterio binario:** meta-test del ratchet verde (archivos registrados) + conformance verde (C9 resuelto: test verifica que select PROPONE DISTINTO según confidence, no solo que no tiene parámetro runtime).

**Flag:** N/A. **Impacto por runtime:** conformance fija la paridad. **Trabajo del operador: ninguno.**

---

### F5 — Traza de telemetría opcional (observabilidad, sin obligación — C11 resuelto)

**Objetivo:** Persistir en metadata del run la decisión del selector (qué confidence se usó y
qué banda se aplicó) para auditar K1/K2, sin crear endpoints nuevos. (C11: la traza se
mostrará en el drawer de ExecutionHistoryPage o como bloque de debugging en plan futuro.)

**Archivo exacto:** `Stacky Agents/backend/api/agents.py` (mismo bloque de F2) — al construir
el run, adjuntar a la metadata existente un sub-dict opcional.

**Diff ilustrativo:** cuando el selector se invocó (flag ON y propuso), agregar a la metadata
que ya viaja al runner / se persiste:
```python
adaptive_trace = {
    "enabled": True,
    "input_confidence": _conf,        # float | None
    "reason": _sel.reason,            # banda aplicada
    "proposed_model": _sel.model,
    "proposed_effort": _sel.effort,
    "final_model": model_override,    # tras clamp
    "final_effort": effort_override,  # tras clamp
}
# Adjuntar bajo metadata["adaptive_selector"] = adaptive_trace (en el dict de metadata ya
# existente que run_agent/runner persiste; NO crear tabla nueva).
```
Con flag OFF o sin propuesta → NO se agrega la clave (mantiene byte-identidad de metadata).

> **C11 Nota:** La traza `metadata["adaptive_selector"]` se muestra en el panel de ejecución
> (ExecutionHistoryPage, drawer) como JSON crudo o un bloque de debugging. No es una UI
> principal en v1; es observabilidad interna. Plan futuro (plan 44 Observatorio) puede
> exponerla en tarjetas de grounding más elaboradas.

**Tests PRIMERO** — ampliar `test_adaptive_selector_wiring.py`:
- `test_trace_present_when_flag_on`: flag ON + confidence=0.2 → la metadata del run incluye
  `adaptive_selector` con `reason` empezando en `"adaptive:"` y `final_model=="claude-opus-4-8"`.
- `test_trace_absent_when_flag_off`: flag OFF → la metadata NO contiene la clave `adaptive_selector`.

**Comando:**
`& .\.venv\Scripts\python.exe -m pytest tests\test_adaptive_selector_wiring.py -q`

**Criterio binario:** ambos tests de traza verdes; con flag OFF la metadata no cambia.

**Flag:** `STACKY_ADAPTIVE_SELECTOR_ENABLED`. **Impacto por runtime:** la traza se persiste igual
para los 3 (metadata es runtime-agnóstica). **Trabajo del operador: ninguno (opt-in default off).**

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|--------|-----------|
| R1 | El confidence histórico del proyecto no representa al brief actual (proyecto heterogéneo) → propuesta subóptima. (C1) | Threshold defensivo: confidence < 0.3 cae a fallback (no amplifica ruido). Override manual del operador siempre gana (G4). El lazo se mejora con datos del siguiente run. |
| R2 | Drift: cambia `_OPUS_ALLOWLIST` o `CLAUDE_CAP_MODEL` y la tabla queda inconsistente. | `assert _MODEL_OPUS in llm_router._OPUS_ALLOWLIST` en import (F1) + reuso de `llm_router.CLAUDE_CAP_MODEL` como constante (no string suelto). |
| R3 | Romper byte-identidad con flag OFF. | F2 salta TODO el bloque con flag OFF; `test_flag_off_is_byte_identical` + `test_run_brief_preflight.py` lo prueban. |
| R4 | El selector pisa un override manual del operador. | G4 por-campo (model y effort por separado); tests `test_operator_*_override_wins` + `test_operator_empty_model_string_not_override` (C3). |
| R5 | Para codex/copilot el `model_override` Claude es inerte → falsa sensación de adaptación de modelo. | Documentado en F3 como degradación controlada; el **effort** sí modula. Tests F3 verifican el comportamiento real (C6). Mapeo a modelos nativos = plan futuro (§6). |
| R6 | `grounding_observatory.build_summary` tiene otra firma de la asumida. (C2) | PASO 0 (PRE-implementación) obliga a VERIFICAR el nombre/firma real antes de escribir código; el helper de I/O es el único punto de acople y está aislado en try/except más específico (C7). |
| R7 | La matriz de efforts soportados por modelo cambia. | F3 fija esperados leyendo `_clamp_effort_for_model` real, no reimplementa la matriz. Tests verifican contra la función real. |
| R7b | Las bandas de confidence son hardcodeadas; si futuro análisis muestra que umbrales deben cambiar, requiere redeploy. | Documentado en F1 que las bandas son constantes código en v1; plan futuro puede elevarlas a config en `config.py` si hay análisis de impacto en K1/K2. Decisión de arquitectura marcada. |
| R8 | Edge cases de clampeo (confidence exacto 0.0/1.0) producen comportamiento inesperado. (C8) | Tests `test_clamped_confidence_high_100_selects_highest_band` + `test_clamped_confidence_low_00_selects_lowest_band` validan. |

---

## 6. Fuera de scope (planes POSTERIORES del top-5)

Este plan SOLO emite y consume la señal de confidence para elegir modelo/effort. **NO** incluye
(son planes separados que dependen de éste como habilitador):

- **Preview de portafolio** (vista anticipada de qué se va a generar antes de gastar): plan posterior.
- **Memoria que empuja** (rechazos → anti-patrones imperativos): es el plan 48, separado.
- **Gate golden ±** (gates correctivos deterministas de épica): planes 49/50/51, separados.
- **Latencia-cero / FA-36** (speculative phase / inyección sin costo): plan separado.
- **Negociación condicionada por confidence** (pedirle al operador decisiones solo cuando el
  confidence es bajo): plan posterior que consume la señal madura de éste.
- **Mapeo de banda a modelos NATIVOS de codex/copilot** (que el "subir modelo" también aplique
  fuera de Claude CLI): plan posterior (R5).

---

## 7. Glosario + Orden de implementación + DoD

### Glosario
- **Confidence de grounding:** número 0.0–1.0 que el BusinessAgent reporta sobre cuán anclada
  está la épica en docs/proceso reales. Se extrae del HTML (`_extract_confidence_from_html`,
  api/tickets.py:5634), se persiste en `epic_summary["confidence"]` y se agrega por proyecto en
  `grounding_observatory`. Marcador `[BAJA CONFIANZA]` sin número → `0.4` (sentinel). Ausente → `None`.
- **[ADICIÓN ARQUITECTO — Segmentación conceptual de confidence (nuevo):]** El selector divide el espacio
  de confianza en **3 bandas conceptuales**:
  - **Muy baja** (< 0.3): "el grounding es ruidoso o ausente"; defensiva: usar defaults o fallback.
  - **Media** (0.3–0.70): "hay anclaje pero es incompleto"; bajar effort/modelo conservativamente.
  - **Muy alta** (≥ 0.75): "anclaje sólido"; ahorrar tokens con Sonnet/low.
  Este framework permite **observabilidad pasiva sin alarmas bloqueantes**: el operador ve el nivel
  de confianza en la telemetría pero nunca es forzado a actuar. Si la confianza es baja, el sistema
  sube esfuerzo y el operador recibe una épica más robusta; puede auditar en el drawer y decidir
  re-correr o aceptar. Si es alta, ahorra. La adaptación es **amplificadora al operador**, no
  sustituta (human-in-the-loop). Este patrón será reutilizado en el top-5: preview de portafolio,
  negociación condicionada, gates de calidad, todos consumirán la misma señal madura de confidence.
- **Effort:** nivel de esfuerzo del CLI ({low, medium, high, xhigh, max}); acotado por modelo
  vía `_clamp_effort_for_model` (api/agents.py:544).
- **Clamp:** red de seguridad que mapea cualquier modelo prohibido (opus/fable fuera de
  allowlist) a `CLAUDE_CAP_MODEL` (`llm_router.clamp_model`, llm_router.py:35). Dueño único de
  qué está permitido.
- **Allowlist (`_OPUS_ALLOWLIST`):** conjunto de modelos Opus exentos del cap, solo con
  `allow_opus=True` (exclusivo de brief→épica). Hoy: `{"claude-opus-4-8"}` (llm_router.py:32).
- **Runtime:** motor de ejecución del agente: `claude_code_cli`, `codex_cli`, `github_copilot`.

### Orden de implementación (numerado, por dependencia)
1. **F0** — flag `STACKY_ADAPTIVE_SELECTOR_ENABLED` (default OFF) + esqueleto del módulo + test del flag.
2. **F1** — `ADAPTIVE_BANDS` + `select()` pura + 13 tests de tabla/bordes.
3. **F2** — `load_last_project_confidence` + cableado en `run_brief` con precedencia (G4) y clamp final (G3) + 7 tests de wiring + no-regresión preflight.
4. **F3** — tabla de fallback por runtime + tests de degradación contra clamps reales.
5. **F4** — registro en ratchet (HARNESS_TEST_FILES + .ps1/.sh) + conformance de paridad.
6. **F5** — traza opcional en metadata + 2 tests de traza.

### Definition of Done (global)
- [ ] `STACKY_ADAPTIVE_SELECTOR_ENABLED` existe, default OFF, documentado en `.env.example`.
- [ ] `services/adaptive_selector.py` con `select()` PURA + `ADAPTIVE_BANDS` + guard de allowlist.
- [ ] Con flag **OFF**: comportamiento byte-idéntico (tests `test_flag_off_is_byte_identical` +
      `test_run_brief_preflight.py` verdes).
- [ ] Con flag **ON**: bajo confidence escala a Opus/max; alto confidence baja a Sonnet/low;
      override manual del operador (model y effort por separado) SIEMPRE gana.
- [ ] Toda propuesta pasa por `clamp_model(allow_opus=True)` + `_clamp_effort_for_model` (G3);
      ninguna propuesta puede escapar la allowlist.
- [ ] La función pura NO recibe `runtime` (conformance verde, G2); degradación por runtime
      documentada y cubierta por clamps.
- [ ] Tests nuevos registrados en ratchet (meta-test plan 49 F4 verde) y en ambos scripts (.ps1/.sh).
- [ ] Traza `metadata["adaptive_selector"]` presente con flag ON, ausente con flag OFF.
- [ ] **Trabajo del operador: ninguno (opt-in default off).**
- [ ] Suite por archivo verde con el python del `.venv` py3.13.
