# Plan 83 — Bounds declarativos para flags numéricas del arnés (validación de rango + rango visible en UI)

**Estado:** PROPUESTO v2 (2026-07-02) — v1 → v2 tras crítica adversarial (`criticar-y-mejorar-plan`)

### Changelog v1 → v2
- **C1:** el aviso "Valor actual fuera de rango" y sus tests se muestran SOLO cuando
  `flag.active && !flag.in_bounds`. Motivo verificado: `read_current()` serializa `0`/`0.0` para
  flags `env_only` sin configurar (harness_flags.py:1936-1942); con `min_value=1` la UI marcaría
  como inválidas decenas de flags intactas (mismo criterio anti-ruido que el Plan 82 C1-v3).
- **C2:** eliminado el hedge de F2 sobre `apply_profile`: VERIFICADO que `apply_profile` valida vía
  `apply_updates` (services/harness_profiles.py:113) y que `detect_profile` también
  (harness_profiles.py:143) tragándose el `ValueError` (144-145) — un bound que invalide un perfil lo
  volvería indetectable en silencio. `test_profiles_values_within_bounds` pasa a criterio binario
  TAMBIÉN de F2.
- **C3:** eliminado el hedge de F3.4: el Panel YA muestra errores del PUT vía `apiError`
  (HarnessFlagsPanel.tsx:200, 214-216); el paso determinista es verificar/ajustar que
  `HarnessFlags.update` en `endpoints.ts` lance `Error(json.error)` espejando el patrón del fetch de
  `applyProfile` (Panel:225-228), con test.
- **C4:** F0.3 ahora es literal: el dict por-flag se construye en `read_current()`
  (harness_flags.py:1948-1961) y la variable local del valor se llama `value` (1937/1944/1946).
- **C5:** receta exacta para `test_apply_updates_no_bounds_unchanged`
  (`monkeypatch.setitem(_REGISTRY_INDEX, ...)` con FlagSpec sintético).
- **C6:** corregida la redacción del último ítem del DoD.
- **[ADICIÓN ARQUITECTO v2]:** chip en el hero "N fuera de rango" (renderizado solo si N>0) que al
  click activa un filtro `onlyOutOfBounds`: triage de un click de los valores heredados inválidos del
  `.env`, con tests.

## 1. Objetivo e impacto

El panel del arnés (`HarnessFlagsPanel`) tiene **29 flags numéricas** (`type="int"` o `"float"` en
`FLAG_REGISTRY`) y hoy NADA valida su rango:

1. **El backend valida solo el tipo.** `_cast` (`Stacky Agents/backend/services/harness_flags.py:2016-2029`)
   acepta cualquier int/float: `STACKY_RAG_CATALOG_TOP_K=-3`, `STACKY_EXEC_VERIFICATION_TIMEOUT_S=0`
   o `STACKY_MAX_CONCURRENT_RUNS=-1` se persisten al `.env` sin error.
2. **Los consumidores se defienden de forma INCONSISTENTE.** Algunos clampan:
   `claude_code_cli_runner.py:983` hace `max(1, int(...))` para `STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS`;
   `context_enrichment.py:800` hace `max(1, int(top_k_raw))`. Otros NO:
   `exec_verification.py:538` pasa `STACKY_EXEC_VERIFICATION_TIMEOUT_S` crudo — un 0 o negativo llega
   al mecanismo de timeout sin defensa. El operador no tiene forma de saber en cuál de los dos mundos
   está cada flag.
3. **La UI no muestra ni limita el rango.** Los inputs numéricos (`HarnessFlagsPanel.tsx:89-113`)
   son `<input type="number">` sin `min`/`max` y sin ningún texto de rango válido junto al control.

**Propuesta:** metadata aditiva `min_value`/`max_value` en `FlagSpec` (default `None` = sin bound),
mapa curado y CONGELADO por test (mismo patrón que el `requires` del Plan 82 F1), validación de rango
**solo en el escritor** (`apply_updates` → 400 claro con el rango), exposición `in_bounds` en
`read_current()` (fail-open) y UI con `min`/`max` + rango visible + aviso "valor fuera de rango" para
valores CONFIGURADOS fuera de rango + chip de triage en el hero.

**KPI/impacto esperado:**
- 0 valores numéricos sin sentido persistibles desde la UI: todo PUT fuera de rango devuelve 400 con
  el rango válido en el mensaje (hoy: se persiste en silencio).
- El operador ve el rango válido de cada flag numérica junto al input, sin abrir código ni docs.
- Valores heredados del `.env` fuera de rango quedan VISIBLES (aviso en la fila + chip en el hero),
  nunca bloqueados.
- Impacto runtime NULO: ningún runner/gate evalúa bounds; los clamps existentes de consumidores NO se
  tocan.

## 2. Por qué ahora / gap que cierra

El Plan 82 (PROPUESTO v3) cierra la semántica de **relaciones** (`requires`), **origen** (`env`) y
**desvío** (modificada / `profile_deltas`). Dejó explícitamente afuera la **validez del valor**: su
sección "Fuera de scope" no la menciona y ninguna fase valida rangos. Este plan es el complemento
exacto: con 29 flags numéricas y defensas inconsistentes en consumidores, un typo (`120` → `12000`,
`8` → `-8`) hoy es un error silencioso que solo aparece como comportamiento raro en runs. Reusa el
patrón ya probado del 82: campo aditivo en `FlagSpec` + mapa curado congelado + serialización en
`read_current()` + presentación en `FlagRow`.

## 3. Principios y guardarraíles (no negociables)

- **Paridad 3 runtimes (Codex CLI / Claude Code CLI / GitHub Copilot Pro):** impacto NULO en los tres.
  `min_value`/`max_value` solo los evalúan `apply_updates` (PUT del panel, `apply_profile` y
  `detect_profile`, ver F2) y `read_current()` (GET del panel). Ningún runner importa estos símbolos.
  Los clamps existentes en consumidores (`claude_code_cli_runner.py:983`,
  `context_enrichment.py:800`) quedan INTACTOS como defensa en profundidad.
- **Fail-loud solo en escritura, fail-open en lectura:** un valor fuera de rango YA persistido en
  `.env` nunca rompe el GET ni un run; solo se marca `in_bounds: false` para que la UI avise. El
  arranque del backend NO valida bounds (cero riesgo de no poder levantar por un `.env` viejo).
- **Cero trabajo extra al operador:** todo informativo/automático. El único cambio de comportamiento
  es que el PUT rechaza valores sin sentido con mensaje claro — eso AHORRA trabajo (antes debuggeaba
  runs raros).
- **Sin flag de comportamiento nueva:** mismo precedente que los planes 62/63/78/82 (cambios de
  panel/metadata sin flag). Rollback = revertir el commit.
- **Gotcha de defaults (regla dura):** NINGÚN `FlagSpec` se toca en su campo `default`. Los campos
  nuevos son aditivos con default `None`. Prohibido pasar `default=False`/`default=True`/`default=<n>`
  a specs existentes o nuevos (rompería `test_default_known_only_for_curated`, lista congelada Plan 63).
- **Bounds LAXOS, no opiniones:** solo se declaran límites que excluyen valores SIN SENTIDO para el
  consumidor real (negativos donde el código asume ≥0, cero donde cero rompe, score fuera de [0,1]).
  PROHIBIDO usar bounds para imponer "valores recomendados".
- **Human-in-the-loop / mono-operador:** sin cambios; es UI + validación de entrada.
- **Backward-compatible:** `min_value=None`/`max_value=None` en todos los specs no listados; el GET
  agrega claves nuevas sin quitar ninguna; el frontend tolera ausencia (`?? null`).
- **Convivencia con el Plan 82 (NO implementado aún):** ambos planes agregan campos a `FlagSpec`,
  claves a `read_current()` y presentación a `FlagRow`. Son independientes y conmutativos: este plan
  referencia SÍMBOLOS (no números de línea absolutos) en los puntos que el 82 desplaza. Si el 82 ya
  está implementado al ejecutar este plan, los campos nuevos van DESPUÉS de `requires`; si no, después
  de `default`.

## 4. Fases

### F0 — Campos `min_value`/`max_value` en FlagSpec + funciones puras + exposición en `read_current()` (backend, TDD)

**Objetivo:** que el registry pueda declarar el rango válido de una flag numérica, con validación
estructural del propio registry y serialización al frontend.

**Archivos:**
- Editar: `Stacky Agents/backend/services/harness_flags.py`
- Crear (test PRIMERO): `Stacky Agents/backend/tests/test_harness_flags_bounds.py`

**Cambios exactos:**

1. En `FlagSpec` (harness_flags.py:19-27) agregar DOS campos al final (después del último campo
   existente — `default`, o `requires` si el Plan 82 ya se implementó):

```python
    min_value: float | None = None  # Plan 83 — mínimo válido inclusive (solo type int/float).
    max_value: float | None = None  # Plan 83 — máximo válido inclusive. None = sin límite.
                                    # Solo los evalúan apply_updates y read_current; NINGÚN runner.
```

2. Agregar dos funciones puras al final del módulo, ANTES de `read_current` (harness_flags.py:1928):

```python
def value_in_bounds(spec: FlagSpec, value: object) -> bool:
    """True si `value` respeta los bounds declarados (o no hay bounds).

    Casos borde (todos deterministas):
    - spec sin bounds (ambos None) → True.
    - spec.type no es "int" ni "float" → True (bounds solo aplican a numéricas).
    - value None o no convertible a float → True (fail-open: nunca marcar
      fuera-de-rango por un bug de datos; el tipo lo valida _cast aparte).
    - comparación INCLUSIVE: min_value <= v <= max_value.
    """
    if spec.min_value is None and spec.max_value is None:
        return True
    if spec.type not in ("int", "float"):
        return True
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return True
    if spec.min_value is not None and v < spec.min_value:
        return False
    if spec.max_value is not None and v > spec.max_value:
        return False
    return True


def validate_bounds_registry() -> list[str]:
    """Valida los bounds declarados en FLAG_REGISTRY. Lista vacía = OK.

    Reglas estructurales:
    R1: bounds solo en specs con type "int" o "float".
    R2: si ambos declarados, min_value <= max_value.
    R3: si el spec declara `default` (no None) numérico, debe cumplir sus propios bounds.
    """
    errors: list[str] = []
    for spec in FLAG_REGISTRY:
        if spec.min_value is None and spec.max_value is None:
            continue
        if spec.type not in ("int", "float"):
            errors.append(f"{spec.key}: bounds declarados sobre type {spec.type!r} (solo int/float)")
            continue
        if spec.min_value is not None and spec.max_value is not None and spec.min_value > spec.max_value:
            errors.append(f"{spec.key}: min_value {spec.min_value} > max_value {spec.max_value}")
        if spec.default is not None and not value_in_bounds(spec, spec.default):
            errors.append(f"{spec.key}: default {spec.default!r} fuera de sus propios bounds")
    return errors
```

3. [C4] En `read_current()` el dict por-flag se construye en `result.append({...})`
   (harness_flags.py:1948-1961) y la variable local con el valor actual se llama `value` (asignada en
   1937/1944 para `env_only` y 1946 vía `getattr(config, spec.key)`). Agregar TRES claves a ese dict,
   después de `"active"`:

```python
            "min_value": spec.min_value,
            "max_value": spec.max_value,
            "in_bounds": value_in_bounds(spec, value),
```

   NO recalcular `value`; usar la misma variable local existente.

   Nota de honestidad del payload: para una flag `env_only` numérica SIN configurar, `read_current()`
   serializa `0`/`0.0` (harness_flags.py:1936-1942); si esa flag tiene `min_value=1`, su `in_bounds`
   viajará `false`. Es CORRECTO en el payload (el valor efectivo 0 está fuera de rango) pero la UI
   NO debe avisar en ese caso: el aviso se gatea por `flag.active` (ver F3, regla C1).

**Tests (escribir PRIMERO, verificar que fallan, luego implementar):**
`Stacky Agents/backend/tests/test_harness_flags_bounds.py`
- `test_flagspec_bounds_default_none` — un `FlagSpec` construido sin bounds tiene
  `min_value is None and max_value is None`.
- `test_value_in_bounds_no_bounds_true` — spec sin bounds → True para -999, 0, 999.
- `test_value_in_bounds_min_only` — spec `min_value=1`: `0 → False`, `1 → True`, `50 → True`.
- `test_value_in_bounds_min_and_max` — spec `min_value=0, max_value=1` (float):
  `-0.1 → False`, `0 → True`, `1 → True`, `1.5 → False`.
- `test_value_in_bounds_non_numeric_fail_open` — spec int con `min_value=1` y value `"abc"`/`None`
  → True.
- `test_value_in_bounds_non_numeric_type_true` — spec type `"csv"` con bounds declarados → True
  (la regla R1 lo reporta aparte).
- `test_validate_bounds_registry_ok` — con el registry real, `validate_bounds_registry() == []`.
- `test_read_current_exposes_bounds_fields` — cada dict de `read_current()` tiene keys `min_value`,
  `max_value`, `in_bounds` (monkeypatchear config exactamente como lo hace
  `tests/test_harness_flags.py` en sus tests de `read_current`).
- El gotcha de defaults NO lleva test nuevo: lo cubre el test EXISTENTE
  `test_default_known_only_for_curated` (lista congelada Plan 63), que se corre como criterio de F0
  (segundo comando de abajo).

**Comando:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests\test_harness_flags_bounds.py -q
.venv\Scripts\python.exe -m pytest tests\test_harness_flags.py -q
```

**Criterio binario:** ambos comandos exit 0; `read_current()[i]` contiene
`min_value`/`max_value`/`in_bounds`.
**Flag:** ninguna (metadata aditiva; ver guardarraíles).
**Runtimes:** impacto nulo en los 3 (ningún runner importa estos símbolos).
**Trabajo del operador:** ninguno.

### F1 — Poblar bounds en el registry (mapa curado y CONGELADO, verificado por consumidor)

**Objetivo:** declarar bounds LAXOS reales para las 29 flags numéricas, verificados contra el código
consumidor — nunca inventados.

**Archivos:**
- Editar: `Stacky Agents/backend/services/harness_flags.py` (solo agregar `min_value=`/`max_value=` a
  specs existentes)
- Editar: `Stacky Agents/backend/tests/test_harness_flags_bounds.py` (test de congelamiento)

**Procedimiento determinista por candidato (obligatorio, sin excepciones):**
Para CADA fila de la tabla, ANTES de agregar bounds:
1. `grep` de la key en `backend/` fuera de `services/harness_flags.py`, `config.py`, `tests/` y
   `.env*` — eso da el/los consumidores reales.
2. Leer el uso: ¿el consumidor trata `0` como caso especial (ej. "0 = desactivado")? ¿clampa ya con
   `max(...)`? ¿un negativo tiene semántica o rompe?
3. Elegir el bound MÁS LAXO que excluya solo valores sin sentido según lo leído. Si `0` es semántica
   válida ("desactivado"), el min es `0`, NO `1`.
4. Si el consumidor acepta razonablemente cualquier valor (o no hay consumidor claro), NO declarar
   bounds y documentar el descarte como comentario en `test_bounds_map_is_frozen`
   (`# descartado Plan 83 F1: <KEY> — <motivo> (<archivo:línea>)`).

**Tabla de candidatos (bound PROPUESTO — el procedimiento de arriba manda; si contradice la tabla,
gana el código y se documenta):**

| Key | min propuesto | max propuesto | Racional esperado |
|---|---|---|---|
| CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES | 0 | — | 0 = sin reintentos |
| CODEX_CLI_AUTOCORRECT_MAX_RETRIES | 0 | — | idem |
| STACKY_CONTEXT_BUDGET_TOKENS | 0 | — | tokens negativos sin sentido |
| STACKY_MEMORY_REVIEW_SWEEP_HOURS | 0 | — | 0 = sin barrido (verificar) |
| STACKY_MEMORY_DIRECTIVE_MAX_CHARS | 0 | — | chars negativos sin sentido |
| STACKY_RUNAWAY_MAX_TURNS | 0 | — | verificar semántica de 0 |
| STACKY_RUNAWAY_MAX_COST_USD | 0 | — | costo negativo sin sentido |
| STACKY_MAX_CONCURRENT_RUNS | 1 | — | 0 bloquearía todo run (verificar) |
| STACKY_SELF_REVIEW_MIN_SCORE | 0 | 1 | score normalizado |
| STACKY_DIGEST_INTERVAL_HOURS | 0 | — | 0 = sin digest (verificar) |
| STACKY_BUDGET_PER_TICKET_USD | 0 | — | presupuesto negativo sin sentido |
| STACKY_EVALS_INTERVAL_HOURS | 0 | — | 0 = sin evals (verificar) |
| STACKY_RUN_CACHE_DAYS | 0 | — | 0 = sin caché (verificar) |
| STACKY_ADO_READ_CACHE_TTL_SEC | 0 | — | 0 = sin caché (verificar) |
| STACKY_ORPHAN_REAPER_INTERVAL_SEC | 0 | — | doc dice "0 = solo al arrancar" (harness_flags.py:786) |
| STACKY_STALL_WATCHDOG_SECONDS | 0 | — | verificar semántica de 0 |
| STACKY_CRITERIA_REPAIR_MAX_RETRIES | 0 | — | 0 = sin pase |
| STACKY_CLI_FEWSHOT_K | 1 | — | K=0 sin sentido con el master ON (verificar) |
| STACKY_TRANSIENT_RUN_RETRY_MAX | 0 | — | 0 = sin retry |
| STACKY_EXEC_VERIFICATION_TIMEOUT_S | 1 | — | exec_verification.py:538 NO clampa; 0 rompe |
| STACKY_EXEC_VERIFICATION_BUDGET_S | 1 | — | idem |
| STACKY_EXEC_REPAIR_MAX_RETRIES | 0 | — | 0 = sin repair |
| STACKY_ACCEPTANCE_CONTRACT_MAX_CHECKS | 1 | — | 0 checks sin sentido (verificar) |
| STACKY_ACCEPTANCE_REPAIR_MAX_RETRIES | 0 | — | 0 = sin repair |
| STACKY_UNBLOCKER_COMPLETED_CAP | 1 | — | cap 0 vacía el panel (verificar) |
| STACKY_RAG_CATALOG_TOP_K | 1 | — | consumidor ya clampa max(1,..) (context_enrichment.py:800) |
| INTENT_PREFLIGHT_AUTO_APPROVE_MIN_CONF | 0 | 1 | confidence normalizada |
| STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS | 1 | — | consumidor clampa max(1,..) (claude_code_cli_runner.py:983) |
| STACKY_ADO_EDIT_SWEEP_HOURS | 0 | — | 0 = sin barrido (verificar) |

Reglas duras de esta fase:
- NO declarar `max_value` salvo rango semántico cerrado real ([0,1] de scores/confidence). Nada de
  máximos "razonables" inventados.
- NO inventar filas fuera de la tabla (las 29 de arriba son TODAS las int/float del registry a la
  fecha; si al implementar hay más, se anotan como
  `# candidato bounds Plan 83 F1 descartado/futuro` y NO se agregan).
- NO tocar `default`, `env_only`, `pair`, `type`, `label`, `description`, `group`, `requires` de
  ningún spec.

**Tests (agregar a `test_harness_flags_bounds.py`):**
- `test_bounds_map_is_frozen` — construir
  `{s.key: (s.min_value, s.max_value) for s in FLAG_REGISTRY if s.min_value is not None or s.max_value is not None}`
  y compararlo con un dict literal EXACTO (las filas que sobrevivieron al procedimiento). Mismo patrón
  que `test_defect_vocabulary_is_frozen` (Plan 61). Los descartes van como comentarios en este test.
- `test_validate_bounds_registry_ok_after_population` — `validate_bounds_registry() == []` con el
  registry poblado.
- `test_profiles_values_within_bounds` — para cada perfil en `PROFILES`
  (`services/harness_profiles.py`) y cada key numérica del perfil presente en `_REGISTRY_INDEX`,
  `value_in_bounds(spec, valor_del_perfil) is True`. [C2] Este test es CRÍTICO: `apply_profile`
  valida vía `apply_updates` (harness_profiles.py:113) y `detect_profile` también
  (harness_profiles.py:143) con `except ValueError: continue` (144-145) — un bound que invalide un
  perfil rompería el POST /profile con 400 Y haría que ese perfil nunca se detecte como activo. Si
  este test falla, el bound está mal elegido; NO se toca el perfil.

**Comando:** el mismo de F0.
**Criterio binario:** exit 0; el mapa congelado coincide 1:1 con el registry; perfiles dentro de bounds.
**Flag:** ninguna. **Runtimes:** impacto nulo. **Trabajo del operador:** ninguno.

### F2 — Validación de rango en el escritor (`apply_updates` → 400 claro)

**Objetivo:** que ningún valor fuera de rango se persista desde la UI, con mensaje accionable.

**Archivos:**
- Editar: `Stacky Agents/backend/services/harness_flags.py`
- Editar: `Stacky Agents/backend/tests/test_harness_flags_bounds.py` (tests PRIMERO)

**Cambio exacto:** en `apply_updates` (harness_flags.py:1965-1985), después de
`result[key] = _cast(spec, raw_value)` agregar:

```python
        if not value_in_bounds(spec, result[key]):
            lo = "-inf" if spec.min_value is None else spec.min_value
            hi = "inf" if spec.max_value is None else spec.max_value
            raise ValueError(
                f"Flag {spec.key!r}: valor {result[key]!r} fuera de rango [{lo}..{hi}]."
            )
```

NO tocar `_cast` (sigue siendo solo-tipo; la separación tipo/rango mantiene `_cast` reutilizable).
El endpoint PUT ya mapea `ValueError → 400` (`api/harness_flags.py:139-141`): cero cambios en la API.

[C2 — flujo VERIFICADO, sin hedge] `apply_updates` tiene TRES callers además del PUT:
- `apply_profile` (services/harness_profiles.py:113): si un perfil violara bounds, el POST /profile
  devolvería 400. Lo previene `test_profiles_values_within_bounds` (F1).
- `detect_profile` (services/harness_profiles.py:143): envuelve en `try/except ValueError: continue`
  (144-145); un perfil fuera de bounds se volvería INDETECTABLE en silencio. Lo previene el mismo test.
Por eso `test_profiles_values_within_bounds` es criterio binario de ESTA fase además de F1.

**Tests:**
- `test_apply_updates_rejects_below_min` — con una key REAL del mapa congelado que tenga `min_value`
  (elegir la primera del dict del test de F1), `apply_updates({key: min-1})` lanza `ValueError` cuyo
  mensaje contiene `"fuera de rango"` y la representación del rango.
- `test_apply_updates_accepts_boundary` — `apply_updates({key: min})` NO lanza (inclusive).
- `test_apply_updates_rejects_above_max` — con una key con `max_value` (ej.
  `STACKY_SELF_REVIEW_MIN_SCORE` si sobrevivió, o la que tenga max en el mapa), valor `max+0.5` lanza.
- `test_apply_updates_no_bounds_unchanged` — [C5] receta exacta: construir un
  `FlagSpec(key="STACKY_TEST_NO_BOUNDS", type="int", label="t", description="t", group="global")`
  sintético e inyectarlo con `monkeypatch.setitem(harness_flags._REGISTRY_INDEX, "STACKY_TEST_NO_BOUNDS", spec)`;
  `apply_updates({"STACKY_TEST_NO_BOUNDS": -5}) == {"STACKY_TEST_NO_BOUNDS": -5}` (acepta negativos
  como hoy).
- `test_put_endpoint_returns_400_out_of_bounds` — vía test client Flask (mismo harness que
  `tests/test_harness_flags.py` usa para el PUT): PUT con valor fuera de rango → status 400 y
  `"fuera de rango"` en `error`; y el `.env` de test NO contiene la key escrita.

**Comando:** el mismo de F0, MÁS re-correr el test de perfiles:
```
.venv\Scripts\python.exe -m pytest tests\test_harness_flags_bounds.py -q -k "profiles_within or apply_updates or put_endpoint"
```
**Criterio binario:** exit 0; PUT fuera de rango → 400 sin persistir;
`test_profiles_values_within_bounds` verde.
**Flag:** ninguna. **Runtimes:** impacto nulo (la validación vive en el endpoint del panel; ningún
runner llama `apply_updates`). **Trabajo del operador:** ninguno.

### F3 — UI: `min`/`max` en inputs, rango visible, aviso "fuera de rango" (gateado por `active`) y chip de triage en el hero

**Objetivo:** que el operador VEA el rango válido y cualquier valor CONFIGURADO fuera de rango, con
triage de un click.

**Archivos:**
- Editar: `Stacky Agents/frontend/src/api/endpoints.ts` — en el tipo `HarnessFlagView` agregar
  `min_value: number | null;`, `max_value: number | null;`, `in_bounds: boolean;` (tolerar ausencia
  con `?? null` / `?? true` si hay parser explícito; si el tipo es estructural directo del JSON, basta
  el tipo). [C3] Además, LEER `HarnessFlags.update` en este archivo: si el `Error` que lanza en fallo
  NO incluye el `error` del body JSON del backend, ajustarlo espejando EXACTAMENTE el patrón del fetch
  de `applyProfile` (HarnessFlagsPanel.tsx:225-228: `if (!r.ok || !json.ok) throw new Error(json.error ?? \`HTTP ${r.status}\`)`),
  para que el mensaje "fuera de rango [..]" del 400 llegue a `apiError` (Panel:200, 214-216) tal cual.
- Editar: `Stacky Agents/frontend/src/components/HarnessFlagsPanel.tsx`
- Editar: `Stacky Agents/frontend/src/components/HarnessFlagsPanel.module.css`
- Editar (test PRIMERO): `Stacky Agents/frontend/src/components/__tests__/HarnessFlagsPanel.test.tsx`

**Cambios exactos en `FlagRow` (HarnessFlagsPanel.tsx:61-190):**
1. En los inputs `type="number"` de las ramas `int` (líneas 89-100) y `float` (102-113) agregar:
   `min={flag.min_value ?? undefined}` y `max={flag.max_value ?? undefined}`.
2. Junto al input numérico (dentro del mismo contenedor del control, después del `<input>`), cuando
   la flag tenga algún bound declarado, renderizar el rango:

```tsx
   {(flag.min_value !== null || flag.max_value !== null) && (
     <span className={styles.boundsHint}>
       {flag.min_value !== null && flag.max_value !== null
         ? `${flag.min_value}–${flag.max_value}`
         : flag.min_value !== null
           ? `≥ ${flag.min_value}`
           : `≤ ${flag.max_value}`}
     </span>
   )}
```

3. [C1] Calcular `const isOutOfBounds = flag.active && flag.in_bounds === false;` y SOLO cuando
   `isOutOfBounds` renderizar debajo de la descripción:

```tsx
   <p className={styles.outOfBoundsNote}>Valor actual fuera de rango válido</p>
```

   Motivo del gate por `active`: una flag `env_only` numérica sin configurar viaja con `value 0` e
   `in_bounds false` si su min es 1 (harness_flags.py:1936-1942); avisar en ese caso sería ruido
   masivo en flags intactas. PROHIBIDO deshabilitar el control por esta condición: el operador lo
   corrige editándolo (el PUT con un valor válido lo sana; el PUT con otro inválido da 400 por F2).
4. **[ADICIÓN ARQUITECTO v2] Chip de triage en el hero:** en el Panel (componente contenedor):
   - Estado nuevo: `const [onlyOutOfBounds, setOnlyOutOfBounds] = useState(false);`
   - Contador: `const outOfBoundsCount = flags.filter((f) => f.active && f.in_bounds === false).length;`
   - En el hero (junto a los `heroStat` existentes, HarnessFlagsPanel.tsx:370-390), SOLO si
     `outOfBoundsCount > 0`, renderizar:

```tsx
   <button
     type="button"
     className={`${styles.outOfBoundsChip} ${onlyOutOfBounds ? styles.outOfBoundsChipActive : ""}`}
     onClick={() => setOnlyOutOfBounds((v) => !v)}
   >
     {outOfBoundsCount} fuera de rango
   </button>
```

   - Extender `matches()` (Panel:246-254) con, como primera condición junto a `onlyActive`:
     `if (onlyOutOfBounds && !(f.active && f.in_bounds === false)) return false;`
     y agregar `onlyOutOfBounds` a las dependencias del `useMemo` de `orderedSections` (Panel:304) y
     al `open` de las secciones igual que `onlyActive`.
   - Si `outOfBoundsCount` pasa a 0 (el operador corrigió todo), el chip desaparece; para no dejar el
     filtro fantasma activo, al renderizar con `outOfBoundsCount === 0 && onlyOutOfBounds`, resetearlo
     (`useEffect` con `if (outOfBoundsCount === 0 && onlyOutOfBounds) setOnlyOutOfBounds(false);`).

**CSS (`HarnessFlagsPanel.module.css`):** `.boundsHint` (mono 11px, color atenuado, margin-left 6px),
`.outOfBoundsNote` (mismo estilo base que `.errorText`, tamaño pequeño), `.outOfBoundsChip` (pill
pequeña con el color de warning ya usado por `.errorText`, cursor pointer) y `.outOfBoundsChipActive`
(misma pill con fondo lleno).

**Tests (Vitest — mismo patrón/mocks que el archivo existente; los datos de flags mock agregan
`min_value`/`max_value`/`in_bounds`):**
- `test_number_input_has_min_max_attrs` — flag int con `min_value:1` renderiza `min="1"` en el input.
- `test_bounds_hint_rendered` — flag con `min_value:0, max_value:1` muestra `0–1`; con solo min
  muestra `≥ 0`.
- `test_no_bounds_no_hint` — flag numérica con ambos `null` no renderiza `.boundsHint`.
- `test_out_of_bounds_note_rendered` — flag con `active:true, in_bounds:false` muestra
  `Valor actual fuera de rango válido`; con `in_bounds:true` no.
- `test_out_of_bounds_note_hidden_when_inactive` — [C1] flag con `active:false, in_bounds:false` NO
  muestra la nota.
- `test_out_of_bounds_control_stays_enabled` — el input NO tiene `disabled` aunque `in_bounds:false`.
- `test_hero_chip_shows_count_and_filters` — con 2 flags `active && !in_bounds`, el hero muestra
  `2 fuera de rango`; click → solo esas flags visibles [ADICIÓN ARQUITECTO v2].
- `test_hero_chip_hidden_when_zero` — sin flags fuera de rango, el chip no se renderiza.

**Comandos (detección determinista, mismo criterio que Plan 82 C4):**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest --version
```
- exit 0 → correr `npx vitest run src/components/__tests__/HarnessFlagsPanel.test.tsx`; ese resultado
  ES el criterio.
- exit ≠ 0 (vitest ausente — situación conocida del repo) → criterio degrada a `npx tsc --noEmit`
  exit 0; los tests quedan escritos para CI y el reporte final DEBE decir "tests de UI escritos, no
  ejecutados (vitest ausente)" SIN marcarlos verdes.

**Criterio binario:** `tsc --noEmit` exit 0; si vitest disponible, los 8 tests verdes.
**Flag:** ninguna. **Runtimes:** impacto nulo (solo UI del panel). **Trabajo del operador:** ninguno.

### F4 — Ratchet: registrar el test nuevo

**Objetivo:** cumplir la regla del Plan 49 F4 (meta-test de cobertura del arnés).

**Archivos:** los DOS scripts que definen `HARNESS_TEST_FILES` (localizar con
`grep -r "HARNESS_TEST_FILES" "Stacky Agents"` — hay variante `.sh` y `.ps1`).
Agregar: `test_harness_flags_bounds.py`.

**Criterio binario:** el meta-test del ratchet pasa
(`grep -rl "HARNESS_TEST_FILES" tests\` para localizar el archivo del meta-test y correr ESE archivo
con `.venv\Scripts\python.exe -m pytest <archivo> -q`, exit 0).
**Flag/Runtimes/Operador:** n/a, ninguno.

## 5. Riesgos y mitigaciones

- **R1: un bound mal elegido rechaza un valor legítimo del operador.** Mitigación: procedimiento de
  verificación por consumidor en F1 (gana el código, no la tabla) + bounds laxos por regla + mapa
  congelado en test + `test_profiles_values_within_bounds` garantiza que off/safe/full siempre aplican
  y siguen detectables (`detect_profile` traga ValueError, harness_profiles.py:144-145).
  Corrección = editar el spec + el literal del test (2 líneas).
- **R2: `.env` heredado con valor fuera de rango rompe el GET o el arranque.** Mitigación: `in_bounds`
  es fail-open y NO bloquea nada; el arranque no evalúa bounds; solo la UI avisa (y solo en flags
  `active`, C1).
- **R3: colisión textual con el Plan 82 (mismos archivos).** Mitigación: campos/claves/notas con
  nombres disjuntos (`min_value`/`max_value`/`in_bounds` vs `requires`/`requires_met`); las
  instrucciones localizan por símbolo, no por línea absoluta; los planes son conmutativos.
- **R4: vitest no instalado localmente.** Mitigación: degradación declarada a `tsc --noEmit` + reporte
  honesto (idéntico a Plan 82 C4).
- **R5: romper `test_default_known_only_for_curated`.** Mitigación: prohibición explícita de tocar
  `default` (guardarraíles + F1 reglas duras) + el test existente corre como criterio de F0/F1.
- **R6: ruido de avisos en flags no configuradas.** Mitigación: gate por `flag.active` en nota y chip
  (C1); el payload `in_bounds` queda honesto para telemetría futura.

## 6. Fuera de scope

- Clampear o corregir valores en runtime de lectura (los clamps existentes de consumidores quedan
  como están; unificarlos sería otro plan).
- Validar bounds al ARRANCAR el backend o al leer `config.py` (fail-open deliberado).
- Bounds para `csv`/`str`/`json` (longitudes, regex): otro dominio.
- Migrar/corregir automáticamente valores fuera de rango ya persistidos (el operador decide).
- `step` dinámico o sliders en la UI.
- Todo lo que ya cubre el Plan 82 (`requires`, badge `env`, modificadas, `profile_deltas`).

## 7. Glosario

- **Arnés (harness):** conjunto de flags/gates/telemetría que gobierna cómo corren los agentes.
- **FlagSpec / FLAG_REGISTRY / `_REGISTRY_INDEX`:** dataclass, tupla e índice key→spec módulo-level en
  `Stacky Agents/backend/services/harness_flags.py` que declaran todas las flags del panel.
- **`_cast`:** función que castea el valor recibido al tipo del spec (harness_flags.py:1998); NO se
  toca en este plan (la validación de rango vive en `apply_updates`).
- **`active`:** campo del payload por-flag (`is_active`, harness_flags.py:1908-1917): el valor
  difiere de su type-zero. Gatea los avisos de UI para no marcar flags intactas.
- **`env_only`:** la flag no es atributo de `Config`; vive en `os.environ` (igual editable por UI).
- **Perfil (off/safe/full):** conjuntos predefinidos en `services/harness_profiles.py`; se aplican con
  `apply_profile` (POST `/api/harness-flags/profile`, `api/harness_flags.py:86`) y se detectan con
  `detect_profile`; AMBOS pasan por `apply_updates` (harness_profiles.py:113 y 143).
- **Ratchet:** meta-test del Plan 49 que exige que todo archivo de test del arnés esté registrado en
  `HARNESS_TEST_FILES` (scripts sh y ps1).
- **Gotcha de defaults:** `default_is_known` cuenta cualquier `default` no-None contra una lista
  congelada de 12 keys (Plan 63); agregar `default=` a un spec rompe ese test.
- **Fail-open:** ante datos raros la función devuelve el valor que NO restringe (True), para que un
  bug de metadata jamás bloquee al operador ni a un run.

## 8. Orden de implementación

1. F0 (backend: campos + funciones puras + serialización, TDD).
2. F1 (poblar mapa con verificación por consumidor + congelamiento + test de perfiles).
3. F2 (validación en `apply_updates` + test del PUT 400).
4. F3 (UI: min/max + rango visible + aviso gateado por active + chip de triage).
5. F4 (ratchet).

## 9. Definición de Hecho (DoD)

- [ ] `test_harness_flags_bounds.py` verde con el venv del repo.
- [ ] `tests/test_harness_flags.py` (existente) sigue verde sin modificar asserts previos.
- [ ] `test_default_known_only_for_curated` sigue verde (ningún `default` nuevo).
- [ ] PUT `/api/harness-flags` con valor fuera de rango → 400 con `"fuera de rango"` y NO persiste.
- [ ] GET `/api/harness-flags` incluye `min_value`, `max_value`, `in_bounds` por flag.
- [ ] Los perfiles off/safe/full aplican sin error y siguen detectables
      (`test_profiles_values_within_bounds` verde).
- [ ] Inputs numéricos del panel con `min`/`max` y rango visible; valor CONFIGURADO fuera de rango
      muestra el aviso y sigue editable; flag no configurada (inactive) NO muestra aviso.
- [ ] Chip "N fuera de rango" en el hero solo cuando N>0; click filtra; N=0 lo oculta y resetea el
      filtro.
- [ ] El mensaje 400 del backend llega textual a la UI (`apiError`).
- [ ] `npx tsc --noEmit` exit 0; tests de Panel escritos (verdes si vitest disponible; si no, reporte
      honesto "no ejecutados").
- [ ] Ratchet verde con `test_harness_flags_bounds.py` registrado (sh + ps1).
- [ ] [C6] Cero cambios fuera del alcance: `git diff` solo toca `services/harness_flags.py`,
      `tests/test_harness_flags_bounds.py`, `endpoints.ts`, `HarnessFlagsPanel.tsx`,
      `HarnessFlagsPanel.module.css`, el test del Panel y los 2 scripts del ratchet. En particular NO
      toca `*_runner.py`, `exec_verification.py`, `context_enrichment.py`, `harness/` de runtime ni
      prompts de agentes.
