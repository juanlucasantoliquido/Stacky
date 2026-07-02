# Plan 83 — Bounds declarativos para flags numéricas del arnés (validación de rango + rango visible en UI)

**Estado:** PROPUESTO v1 (2026-07-02)

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
valores ya persistidos.

**KPI/impacto esperado:**
- 0 valores numéricos sin sentido persistibles desde la UI: todo PUT fuera de rango devuelve 400 con
  el rango válido en el mensaje (hoy: se persiste en silencio).
- El operador ve el rango válido de cada flag numérica junto al input, sin abrir código ni docs.
- Valores heredados del `.env` fuera de rango quedan VISIBLES (aviso en la fila), nunca bloqueados.
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
  `min_value`/`max_value` solo los evalúan `apply_updates` (PUT del panel) y `read_current()` (GET del
  panel). Ningún runner importa estos símbolos. Los clamps existentes en consumidores
  (`claude_code_cli_runner.py:983`, `context_enrichment.py:800`) quedan INTACTOS como defensa en
  profundidad.
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

2. Agregar dos funciones puras al final del módulo, ANTES de `read_current` (localizarla con grep de
   `def read_current`):

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

3. En `read_current()` (localizar el dict por-flag donde se serializan `"key"`, `"value"`, `"active"`,
   `"env_only"`, `"default"`; harness_flags.py:~1948-1961 en el estado actual) agregar tres claves al
   dict de cada flag:

```python
            "min_value": spec.min_value,
            "max_value": spec.max_value,
            "in_bounds": value_in_bounds(spec, value),
```

   donde `value` es la MISMA variable local que ya se serializa como `"value"` de esa flag (no
   recalcular).

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
  `value_in_bounds(spec, valor_del_perfil) is True` (los perfiles off/safe/full deben poder aplicarse
  siempre; si este test falla, el bound está mal elegido, NO se toca el perfil).

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
`apply_profile` usa `apply_updates` o escribe directo — verificar con grep `apply_updates` en
`services/harness_profiles.py`; si aplica valores vía `apply_updates`, el test
`test_profiles_values_within_bounds` de F1 garantiza que ningún perfil se rompe.

**Tests:**
- `test_apply_updates_rejects_below_min` — con una key REAL del mapa congelado que tenga `min_value`
  (elegir la primera del dict del test de F1), `apply_updates({key: min-1})` lanza `ValueError` cuyo
  mensaje contiene `"fuera de rango"` y la representación del rango.
- `test_apply_updates_accepts_boundary` — `apply_updates({key: min})` NO lanza (inclusive).
- `test_apply_updates_rejects_above_max` — con una key con `max_value` (ej.
  `STACKY_SELF_REVIEW_MIN_SCORE` si sobrevivió, o la que tenga max en el mapa), valor `max+0.5` lanza.
- `test_apply_updates_no_bounds_unchanged` — una key int SIN bounds (si todas quedaron con bounds,
  usar un `FlagSpec` sintético vía monkeypatch de `_REGISTRY_INDEX`) acepta negativos como hoy.
- `test_put_endpoint_returns_400_out_of_bounds` — vía test client Flask (mismo harness que
  `tests/test_harness_flags.py` usa para el PUT): PUT con valor fuera de rango → status 400 y
  `"fuera de rango"` en `error`; y el `.env` de test NO contiene la key escrita.

**Comando:** el mismo de F0.
**Criterio binario:** exit 0; PUT fuera de rango → 400 sin persistir.
**Flag:** ninguna. **Runtimes:** impacto nulo (la validación vive en el endpoint del panel; ningún
runner llama `apply_updates`). **Trabajo del operador:** ninguno.

### F3 — UI: `min`/`max` en inputs, rango visible y aviso "fuera de rango"

**Objetivo:** que el operador VEA el rango válido y cualquier valor heredado fuera de rango.

**Archivos:**
- Editar: `Stacky Agents/frontend/src/api/endpoints.ts` — en el tipo `HarnessFlagView` agregar
  `min_value: number | null;`, `max_value: number | null;`, `in_bounds: boolean;` (tolerar ausencia
  con `?? null` / `?? true` si hay parser explícito; si el tipo es estructural directo del JSON, basta
  el tipo).
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

3. Cuando `flag.in_bounds === false` (valor heredado del `.env` fuera de rango), renderizar debajo de
   la descripción:

```tsx
   <p className={styles.outOfBoundsNote}>Valor actual fuera de rango válido</p>
```

   PROHIBIDO deshabilitar el control por esta condición: el operador lo corrige editándolo (el PUT
   con un valor válido lo sana; el PUT con otro inválido da 400 por F2).
4. El manejo de error del PUT: verificar que el error 400 del backend ya se muestra (buscar cómo el
   Panel muestra `update.error` / respuesta `!ok` de la mutación, HarnessFlagsPanel.tsx:208-311). Si
   el Panel hoy NO muestra el `error` del body en fallos del PUT, agregar un `<div className={styles.errorText}>`
   con el mensaje bajo la barra de acciones (render mínimo, sin librería nueva).

**CSS (`HarnessFlagsPanel.module.css`):** `.boundsHint` (mono 11px, color atenuado, margin-left 6px),
`.outOfBoundsNote` (mismo estilo base que `.errorText`, tamaño pequeño).

**Tests (Vitest — mismo patrón/mocks que el archivo existente; los datos de flags mock agregan
`min_value`/`max_value`/`in_bounds`):**
- `test_number_input_has_min_max_attrs` — flag int con `min_value:1` renderiza `min="1"` en el input.
- `test_bounds_hint_rendered` — flag con `min_value:0, max_value:1` muestra `0–1`; con solo min
  muestra `≥ 0`.
- `test_no_bounds_no_hint` — flag numérica con ambos `null` no renderiza `.boundsHint`.
- `test_out_of_bounds_note_rendered` — flag con `in_bounds:false` muestra
  `Valor actual fuera de rango válido`; con `in_bounds:true` no.
- `test_out_of_bounds_control_stays_enabled` — el input NO tiene `disabled` aunque `in_bounds:false`.

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

**Criterio binario:** `tsc --noEmit` exit 0; si vitest disponible, los 5 tests verdes.
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
  congelado en test + `test_profiles_values_within_bounds` garantiza que off/safe/full siempre aplican.
  Corrección = editar el spec + el literal del test (2 líneas).
- **R2: `.env` heredado con valor fuera de rango rompe el GET o el arranque.** Mitigación: `in_bounds`
  es fail-open y NO bloquea nada; el arranque no evalúa bounds; solo la UI avisa.
- **R3: colisión textual con el Plan 82 (mismos archivos).** Mitigación: campos/claves/notas con
  nombres disjuntos (`min_value`/`max_value`/`in_bounds` vs `requires`/`requires_met`); las
  instrucciones localizan por símbolo, no por línea absoluta; los planes son conmutativos.
- **R4: vitest no instalado localmente.** Mitigación: degradación declarada a `tsc --noEmit` + reporte
  honesto (idéntico a Plan 82 C4).
- **R5: romper `test_default_known_only_for_curated`.** Mitigación: prohibición explícita de tocar
  `default` (guardarraíles + F1 reglas duras) + el test existente corre como criterio de F0/F1.

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
- **`env_only`:** la flag no es atributo de `Config`; vive en `os.environ` (igual editable por UI).
- **Perfil (off/safe/full):** conjuntos predefinidos en `services/harness_profiles.py`; se aplican con
  `apply_profile` (POST `/api/harness-flags/profile`, `api/harness_flags.py:86`).
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
4. F3 (UI: min/max + rango visible + aviso fuera de rango).
5. F4 (ratchet).

## 9. Definición de Hecho (DoD)

- [ ] `test_harness_flags_bounds.py` verde con el venv del repo.
- [ ] `tests/test_harness_flags.py` (existente) sigue verde sin modificar asserts previos.
- [ ] `test_default_known_only_for_curated` sigue verde (ningún `default` nuevo).
- [ ] PUT `/api/harness-flags` con valor fuera de rango → 400 con `"fuera de rango"` y NO persiste.
- [ ] GET `/api/harness-flags` incluye `min_value`, `max_value`, `in_bounds` por flag.
- [ ] Los perfiles off/safe/full aplican sin error (`test_profiles_values_within_bounds` verde).
- [ ] Inputs numéricos del panel con `min`/`max` y rango visible; valor heredado fuera de rango
      muestra el aviso y sigue editable.
- [ ] `npx tsc --noEmit` exit 0; tests de Panel escritos (verdes si vitest disponible; si no, reporte
      honesto "no ejecutados").
- [ ] Ratchet verde con `test_harness_flags_bounds.py` registrado (sh + ps1).
- [ ] Cero cambios en runners/gates/prompts y cero cambios en los clamps existentes de consumidores:
      `git diff` no toca `*_runner.py` (salvo nada), `harness/` de runtime, `exec_verification.py`,
      `context_enrichment.py` ni prompts de agentes.
