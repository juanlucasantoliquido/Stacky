# Plan 82 — Claridad de configuración del arnés (dependencias visibles, origen del valor y desvío de perfil)

**Estado:** PROPUESTO v2 (2026-07-02) — v1 → v2 tras crítica adversarial (`criticar-y-mejorar-plan`)

### Changelog v1 → v2
- **C1:** eliminado el hedge sobre `_REGISTRY_INDEX`: el símbolo EXISTE (lo usa `apply_updates`,
  harness_flags.py:1979); F0 lo reusa sin condicionales.
- **C2:** eliminado el caso de test convoluto `test_no_flagspec_gains_explicit_default`; el gotcha
  queda cubierto por el test existente `test_default_known_only_for_curated`, que pasa a ser criterio
  binario explícito de F0 y del DoD.
- **C3:** F4 reescrita sin hedge: se crea SIEMPRE el helper `_current_value(key)` en
  `harness_profiles.py`, `detect_profile()` pasa a consumirlo, y se localizan/corren los tests
  existentes de perfiles con comando determinista.
- **C4:** detección determinista de vitest en F2/F3: `npx vitest --version` (exit 0 = correr tests;
  exit ≠0 = degradar a `tsc --noEmit` y reportarlo SIN marcar verde).
- **C5:** los candidatos de F1 descartados se documentan como comentario en el test de congelamiento
  (no en el commit message).
- **C6:** explicitado que una flag gestionada como `pair` no renderiza fila propia (Panel:70-71), por
  lo que su `requires` no tiene efecto visual y se descarta si falla la verificación.
- **C7 + [ADICIÓN ARQUITECTO]:** F2 ahora muestra la KEY técnica de la env var en cada fila (mono +
  click-copy) y F3 agrega el filtro "Solo modificadas" junto a "Solo activas".

## 1. Objetivo e impacto

El operador configura ~142 flags del arnés desde `HarnessFlagsPanel` (planes 33/62/63/78). Hoy el panel
NO muestra tres cosas que hacen la configuración confusa y propensa a error silencioso:

1. **Dependencias master→hija invisibles.** `FlagSpec` solo tiene el campo `pair` para el patrón
   bool+CSV (`Stacky Agents/backend/services/harness_flags.py:25`). No existe un campo genérico
   `requires`: el operador puede setear `STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS=5` con
   `STACKY_QUALITY_CONVERGENCE_ENABLED=OFF` y la flag queda **muerta en silencio** (nadie la lee).
   Lo mismo con `STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH` (harness_flags.py:1862) respecto de su
   master `STACKY_CODEBASE_MEMORY_MCP_ENABLED` (harness_flags.py:1833): el `pair` cubre solo a
   `*_PROJECTS` (harness_flags.py:1858), no al binary path ni a ningún otro parámetro hijo.
2. **`env_only` viaja pero no se ve.** `read_current()` serializa `env_only` (harness_flags.py:1955)
   pero `FlagRow` en `HarnessFlagsPanel.tsx:61-190` nunca lo renderiza. El operador no sabe qué flags
   viven solo en `os.environ`/`.env` (se aplican en caliente vía `_write_env`,
   `Stacky Agents/backend/api/harness_flags.py:32-68`) versus las que son atributo de `Config`.
3. **"Personalizado" sin diff ni noción de desvío.** El hero muestra `Perfil: personalizado` cuando
   `detect_profile()` devuelve `None` (`HarnessFlagsPanel.tsx:370`, `api/harness_flags.py:81`), pero
   no dice **cuántas** flags se apartan del default ni **qué tan lejos** está de off/safe/full. El
   badge `def:` existe por flag (Panel:165-167) pero no hay indicador "modificada" ni contador por
   categoría.

**KPI/impacto esperado:**
- 0 "flags muertas" configurables sin aviso: toda hija con master OFF muestra "sin efecto — requiere X".
- El operador identifica de un vistazo qué flags están fuera de default (badge + contador por categoría
  + total en hero), sin abrir cada sección.
- Cero cambios de comportamiento de runs: es un plan de **metadata + presentación**, impacto runtime NULO.

## 2. Por qué ahora / gap que cierra

Los planes 62/63 (categorías + búsqueda + badge `def:`) y 78 (hero, tier Simple/Experto, intent) ya
resolvieron la **navegación**. Lo que quedó abierto es la **semántica**: relaciones entre flags,
origen del valor y desvío respecto de defaults/perfiles. Con 142 flags y creciendo ~3 por plan, cada
plan nuevo (79/80/81 agregaron 6 flags) agrava el costo de descubrir a mano "¿esta flag hace algo si
no prendo la otra?". El sustrato ya existe: `pair` demuestra el patrón (Panel:174-187 deshabilita el
CSV si el bool está OFF), `default_known`/`default` ya viajan (harness_flags.py:1958-1959),
`detect_profile()` ya existe (`services/harness_profiles.py`). Este plan generaliza lo probado.

## 3. Principios y guardarraíles (no negociables)

- **Paridad 3 runtimes (Codex CLI / Claude Code CLI / GitHub Copilot Pro):** impacto NULO en los tres.
  Ningún runner lee `requires`; solo cambian el registry (metadata aditiva), el GET del panel y el TSX.
  No hay degradación posible porque no hay rama de comportamiento nueva en tiempo de run.
- **Cero trabajo extra al operador:** todo es informativo/automático. Ningún paso manual nuevo.
  Los controles NUNCA se bloquean por `requires` (el operador puede preconfigurar una hija antes de
  prender el master); solo se informa.
- **Sin flag de comportamiento nueva:** este plan NO introduce flags runtime (mismo precedente que los
  planes 62/63 y 78, que fueron cambios de presentación sin flag). No hay nada que apagar porque no
  altera runs; el rollback es revertir el commit.
- **Gotcha de defaults (regla dura):** NINGÚN `FlagSpec` se toca en su campo `default`. El campo nuevo
  `requires` es aditivo con default `None`. Prohibido pasar `default=False`/`default=True` a specs
  existentes o nuevos (rompería `test_default_known_only_for_curated`, lista congelada Plan 63).
- **Human-in-the-loop / mono-operador:** sin cambios; es UI informativa.
- **Backward-compatible:** `requires=None` en todos los specs no listados; el GET agrega claves nuevas
  sin quitar ninguna; frontend tolera `requires` ausente (`?? null`).

## 4. Fases

### F0 — Campo `requires` en FlagSpec + `requires_met` + exposición en `read_current()` (backend, TDD)

**Objetivo:** que el registry pueda declarar "esta flag solo tiene efecto si la key X (bool) está ON",
con validación estructural congelada y serialización al frontend.

**Archivos:**
- Editar: `Stacky Agents/backend/services/harness_flags.py`
- Crear (test PRIMERO): `Stacky Agents/backend/tests/test_harness_flags_requires.py`

**Cambios exactos:**

1. En `FlagSpec` (harness_flags.py:19-27) agregar UN campo al final, después de `default`:

```python
    requires: str | None = None  # Plan 82 — key de una flag bool que debe estar ON para que
                                 # esta flag tenga efecto. None = sin dependencia. Solo
                                 # informativo para la UI; NINGÚN runner lo evalúa.
```

2. Agregar dos funciones puras al final del módulo (antes de `read_current`):

```python
def requires_met(spec: FlagSpec, values_by_key: dict[str, object]) -> bool:
    """True si la dependencia declarada está satisfecha (o no hay dependencia).

    values_by_key: mapa key→valor actual (el que arma read_current).
    Casos borde:
    - spec.requires is None → True.
    - la key requerida no está en values_by_key → True (fail-open: nunca
      marcar 'sin efecto' por un bug de datos).
    - valor del master truthy (bool True) → True; False/None/'' → False.
    """
    if spec.requires is None:
        return True
    master_value = values_by_key.get(spec.requires)
    if master_value is None and spec.requires not in values_by_key:
        return True
    return bool(master_value)


def validate_requires_graph() -> list[str]:
    """Valida el grafo de dependencias del registry. Devuelve lista de errores ('' vacía = OK).

    Reglas (todas estructurales, deterministas):
    R1: spec.requires debe ser la key de un FlagSpec existente en FLAG_REGISTRY.
    R2: el master apuntado debe tener type == 'bool'.
    R3: prohibida la auto-referencia (spec.requires != spec.key).
    R4: profundidad máxima 1 — un master apuntado NO puede tener a su vez requires
        (sin cadenas ni ciclos por construcción).
    """
    errors: list[str] = []
    for spec in FLAG_REGISTRY:
        if spec.requires is None:
            continue
        master = _REGISTRY_INDEX.get(spec.requires)
        if master is None:
            errors.append(f"{spec.key}: requires apunta a key inexistente {spec.requires!r}")
            continue
        if master.type != "bool":
            errors.append(f"{spec.key}: requires apunta a {spec.requires} de tipo {master.type!r}, debe ser bool")
        if spec.requires == spec.key:
            errors.append(f"{spec.key}: requires auto-referencial")
        if master.requires is not None:
            errors.append(f"{spec.key}: cadena prohibida — {spec.requires} también declara requires")
    return errors
```

   Nota [C1]: `_REGISTRY_INDEX` EXISTE como índice key→spec módulo-level (lo usa `apply_updates`,
   harness_flags.py:1979). Reutilizarlo tal cual; NO crear otro índice.

3. En `read_current()` (harness_flags.py:1948-1961) agregar al dict de cada flag, después de
   `"active"`:

```python
            "requires": spec.requires,
            "requires_met": True,   # se corrige en el pase de abajo
```

   y, tras construir `result`, un pase final (los valores ya están todos calculados):

```python
    values_by_key = {r["key"]: r["value"] for r in result}
    by_key = {s.key: s for s in FLAG_REGISTRY}
    for r in result:
        r["requires_met"] = requires_met(by_key[r["key"]], values_by_key)
    return result
```

**Tests (escribir PRIMERO, verificar que fallan, luego implementar):**
`Stacky Agents/backend/tests/test_harness_flags_requires.py`
- `test_flagspec_requires_default_none` — un `FlagSpec` construido sin `requires` tiene `requires is None`.
- `test_requires_met_none_is_true` — spec sin requires → `requires_met(...) is True`.
- `test_requires_met_master_on` — spec con `requires="X"`, `values={"X": True}` → True.
- `test_requires_met_master_off` — `values={"X": False}` → False; `values={"X": ""}` → False.
- `test_requires_met_master_missing_fail_open` — `values={}` → True.
- `test_validate_requires_graph_empty_registry_ok` — con el registry real, `validate_requires_graph() == []`.
- `test_read_current_exposes_requires_fields` — cada dict de `read_current()` tiene keys `requires` y
  `requires_met` (monkeypatchear config como hace `tests/test_harness_flags.py`).
- [C2] El gotcha de defaults NO lleva test nuevo aquí: lo cubre el test EXISTENTE
  `test_default_known_only_for_curated` (lista congelada Plan 63), que se corre como parte del
  criterio de F0 (está dentro de `tests\test_harness_flags.py`, segundo comando de abajo).

**Comando:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests\test_harness_flags_requires.py -q
.venv\Scripts\python.exe -m pytest tests\test_harness_flags.py -q
```

**Criterio binario:** ambos comandos exit 0 (el segundo incluye `test_default_known_only_for_curated`
verde = gotcha intacto); `read_current()[i]` contiene `requires`/`requires_met`.
**Flag:** ninguna (metadata aditiva; ver guardarraíles).
**Runtimes:** impacto nulo en los 3 (ningún runner importa estos símbolos).
**Trabajo del operador:** ninguno.

### F1 — Poblar `requires` en el registry (mapa curado y CONGELADO)

**Objetivo:** declarar las dependencias master→hija reales, verificadas contra el código consumidor.

**Archivos:**
- Editar: `Stacky Agents/backend/services/harness_flags.py` (solo agregar `requires=...` a specs existentes)
- Editar: `Stacky Agents/backend/tests/test_harness_flags_requires.py` (agregar el test de congelamiento)

**Procedimiento determinista por candidato (obligatorio, sin excepciones):**
Para CADA fila de la tabla de abajo, ANTES de agregar `requires`:
1. `grep` de la key hija en `backend/` (fuera de `services/harness_flags.py` y `tests/`).
2. Abrir el consumidor y verificar que la lectura de la hija está dentro de (o después de) un chequeo
   del master (patrón `if <master>: ... <leer hija>` o retorno temprano si master OFF).
3. Si el consumidor NO gatea por el master (la hija tiene efecto propio), NO agregar `requires` a esa
   fila y [C5] documentar el descarte como comentario en `test_requires_map_is_frozen`
   (`# descartado Plan 82 F1: <KEY> — consumo no gateado por <MASTER> (<archivo:línea>)`).

**Tabla de candidatos (hija → master esperado):**

| Hija | Master | Fuente del vínculo |
|---|---|---|
| CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES | CLAUDE_CODE_CLI_AUTOCORRECT_ENABLED | naming + runner claude |
| CODEX_CLI_AUTOCORRECT_MAX_RETRIES | CODEX_CLI_AUTOCORRECT_ENABLED | naming + runner codex |
| STACKY_CONTEXT_BUDGET_TOKENS | STACKY_CONTEXT_BUDGET_ENABLED | Plan arnés (budget) |
| STACKY_RUN_ADVISOR_ENFORCE | STACKY_RUN_ADVISOR_ENABLED | V2 arnés |
| STACKY_CRITERIA_REPAIR_MAX_RETRIES | STACKY_CRITERIA_REPAIR_ENABLED | Plan 29 |
| STACKY_CLI_FEWSHOT_K | STACKY_CLI_FEWSHOT_ENABLED | Plan 29 Q1.2 |
| STACKY_TRANSIENT_RUN_RETRY_MAX | STACKY_TRANSIENT_RUN_RETRY_ENABLED | Plan 28 |
| STACKY_EXEC_VERIFICATION_MODE | STACKY_EXEC_VERIFICATION_ENABLED | Plan 31 |
| STACKY_EXEC_VERIFICATION_TIMEOUT_S | STACKY_EXEC_VERIFICATION_ENABLED | Plan 31 |
| STACKY_EXEC_VERIFICATION_BUDGET_S | STACKY_EXEC_VERIFICATION_ENABLED | Plan 31 |
| STACKY_EXEC_REPAIR_MAX_RETRIES | STACKY_EXEC_REPAIR_ENABLED | Plan 31 E1.1 |
| STACKY_FAKE_GREEN_GUARD_HARD | STACKY_FAKE_GREEN_GUARD_ENABLED | Plan 31 E1.2 |
| STACKY_ACCEPTANCE_CONTRACT_MODE | STACKY_ACCEPTANCE_CONTRACT_ENABLED | Plan 32 |
| STACKY_ACCEPTANCE_CONTRACT_MAX_CHECKS | STACKY_ACCEPTANCE_CONTRACT_ENABLED | Plan 32 |
| STACKY_ACCEPTANCE_REPAIR_MAX_RETRIES | STACKY_ACCEPTANCE_REPAIR_ENABLED | Plan 32 |
| STACKY_RAG_CATALOG_TOP_K | STACKY_RAG_CATALOG_ENABLED | Plan 64 |
| INTENT_PREFLIGHT_AUTO_APPROVE | INTENT_PREFLIGHT_ENABLED | intent preflight |
| INTENT_PREFLIGHT_AUTO_APPROVE_MIN_CONF | INTENT_PREFLIGHT_ENABLED | intent preflight |
| STACKY_TASK_GATE_BLOCKING | STACKY_TASK_GATE_ENABLED | Plan 61 |
| STACKY_SPECULATIVE_MODE | STACKY_SPECULATIVE_ENABLED | Plan 57 |
| STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS | STACKY_QUALITY_CONVERGENCE_ENABLED | Plan 58 |
| STACKY_ADO_EDIT_SWEEP_HOURS | STACKY_ADO_EDIT_LEARNING_ENABLED | Plan 60 |
| STACKY_MIGRATOR_EPIC_POLICY | STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED | Plan 74 |
| STACKY_CODEBASE_MEMORY_MCP_BINARY_PATH | STACKY_CODEBASE_MEMORY_MCP_ENABLED | Plan 80 (harness_flags.py:1862→1833) |
| STACKY_CODEBASE_MEMORY_MCP_PROJECTS | STACKY_CODEBASE_MEMORY_MCP_ENABLED | ya tiene pair (1858); requires refuerza |
| STACKY_EPIC_CATALOG_GATE_ENABLED | STACKY_EPIC_GATE_ENABLED | Plan 51 (verificar en epic_gate.py) |

Reglas duras de esta fase:
- NO agregar `requires` a las `*_PROJECTS` que ya se renderizan como `pair` de otro bool, EXCEPTO
  `STACKY_CODEBASE_MEMORY_MCP_PROJECTS` que se lista arriba (el `pair` ya la deshabilita en UI,
  Panel:181; el `requires` solo la hace consistente en el payload — si el paso 2 del procedimiento
  falla para ella, se descarta sin más). [C6] Tener presente que una flag gestionada como `pair` NO
  renderiza fila propia (`FlagRow` devuelve `null`, HarnessFlagsPanel.tsx:70-71): su `requires` no
  produce efecto visual, solo consistencia del payload.
- NO inventar filas fuera de la tabla. Si durante el grep aparece otra dependencia evidente, se anota
  como comentario `# candidato requires Plan 82 F1 descartado/futuro` y NO se agrega.
- NO tocar `default`, `env_only`, `pair`, `type`, `label`, `description`, `group` de ningún spec.

**Test de congelamiento (agregar a `test_harness_flags_requires.py`):**
- `test_requires_map_is_frozen` — construir `{s.key: s.requires for s in FLAG_REGISTRY if s.requires}`
  y compararlo con un dict literal EXACTO escrito en el test (las filas que sobrevivieron al
  procedimiento). Cualquier alta/baja futura debe tocar el test (mismo patrón que
  `test_defect_vocabulary_is_frozen` del Plan 61).
- `test_validate_requires_graph_ok_after_population` — `validate_requires_graph() == []` con el
  registry ya poblado.

**Comando:** el mismo de F0 (ambos archivos de test).
**Criterio binario:** exit 0; el mapa congelado del test coincide 1:1 con el registry.
**Flag:** ninguna. **Runtimes:** impacto nulo. **Trabajo del operador:** ninguno.

### F2 — UI: aviso "sin efecto — requiere X" + badge de origen `env`

**Objetivo:** que el operador VEA la dependencia y el origen del valor sin cambiar ningún control.

**Archivos:**
- Editar: `Stacky Agents/frontend/src/api/endpoints.ts` — en el tipo `HarnessFlagView` agregar
  `requires: string | null;` y `requires_met: boolean;` (y tolerar ausencia con `?? null`/`?? true`
  donde se parsee, si hay parser explícito; si el tipo es estructural directo del JSON, basta el tipo).
- Editar: `Stacky Agents/frontend/src/components/HarnessFlagsPanel.tsx`
- Editar: `Stacky Agents/frontend/src/components/HarnessFlagsPanel.module.css`
- Editar (test PRIMERO): `Stacky Agents/frontend/src/components/__tests__/HarnessFlagsPanel.test.tsx`

**Cambios exactos en `FlagRow` (Panel:61-190):**
1. Calcular master para el aviso: `const requiresMaster = flag.requires ? allFlags.find(f => f.key === flag.requires) : null;`
2. Después del `<p className={styles.flagDesc}>` (línea 169) renderizar, SOLO cuando
   `flag.requires && !flag.requires_met`:

```tsx
   <p className={styles.requiresNote}>
     Sin efecto: requiere “{requiresMaster?.label ?? flag.requires}” activada
   </p>
```

3. En el contenedor raíz de la fila (línea 161) agregar la clase condicional
   `${flag.requires && !flag.requires_met ? styles.inertRow : ""}` (CSS: `opacity: 0.55`).
   PROHIBIDO poner `disabled` en los controles por esta condición: el operador puede editar igual.
4. Badge de origen junto al `defaultBadge` (líneas 165-167): cuando `flag.env_only === true`
   renderizar `<span className={styles.envBadge} title="Vive solo en .env/os.environ (se aplica en caliente); no es atributo de Config">env</span>`.
5. **[ADICIÓN ARQUITECTO — C7]** Mostrar la KEY técnica de la env var en la fila: debajo del
   `<p className={styles.flagDesc}>` renderizar

```tsx
   <code
     className={styles.flagKey}
     title="Click para copiar la key"
     onClick={() => { void navigator.clipboard?.writeText(flag.key); }}
   >
     {flag.key}
   </code>
```

   CSS `.flagKey`: fuente mono, tamaño ~11px, color atenuado, `cursor: pointer`. Hoy la fila solo
   muestra `label` (Panel:164) y el operador no puede correlacionar la fila con `.env`, docs o planes.

**CSS (`HarnessFlagsPanel.module.css`):** agregar `.requiresNote` (texto pequeño, color de warning ya
usado por `.errorText` pero en tono atenuado), `.inertRow { opacity: 0.55; }`, `.envBadge` (mismo
estilo base que `.defaultBadge`, otro color de fondo), `.flagKey` (mono 11px atenuado, cursor pointer).

**Tests (Vitest — mismo patrón/mocks que el archivo existente):**
- `test_shows_requires_note_when_master_off` — flag hija con `requires_met:false` renderiza el texto
  `Sin efecto: requiere`.
- `test_hides_requires_note_when_master_on` — con `requires_met:true` NO aparece.
- `test_child_control_stays_enabled_when_master_off` — el input de la hija NO tiene `disabled` aunque
  `requires_met:false`.
- `test_env_badge_rendered_for_env_only` — flag con `env_only:true` muestra el badge `env`; con
  `env_only:false` no.
- `test_flag_key_rendered_in_row` — la fila muestra el texto exacto de `flag.key`.

**Comandos [C4 — detección determinista]:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest --version
```
- Si exit 0 → correr `npx vitest run src/components/__tests__/HarnessFlagsPanel.test.tsx` y ese
  resultado ES el criterio.
- Si exit ≠ 0 (vitest no instalado — situación conocida del repo) → el criterio degrada a
  `npx tsc --noEmit` exit 0; los tests quedan escritos y nombrados para CI y el reporte final DEBE
  decir "tests de UI escritos, no ejecutados (vitest ausente)" SIN marcarlos verdes.

**Criterio binario:** `tsc --noEmit` exit 0; si vitest disponible, 4 tests verdes.
**Flag:** ninguna. **Runtimes:** impacto nulo (solo UI del panel). **Trabajo del operador:** ninguno.

### F3 — UI: badge "modificada" + contador por categoría + total en hero

**Objetivo:** ver de un vistazo qué se apartó de los defaults, por flag, por categoría y global.

**Archivos:**
- Editar: `Stacky Agents/frontend/src/components/harnessVisuals.ts` — agregar función pura exportada:

```ts
export function isModifiedFromDefault(flag: { default_known: boolean; default: unknown; value: unknown; type: string }): boolean {
  if (!flag.default_known) return false;
  // Normalización por tipo para evitar falsos positivos "" vs null y 0 vs "0"
  const norm = (v: unknown): string => {
    if (flag.type === "bool") return String(Boolean(v));
    if (v === null || v === undefined) return "";
    return String(v);
  };
  return norm(flag.value) !== norm(flag.default);
}
```

- Editar: `Stacky Agents/frontend/src/components/HarnessFlagsPanel.tsx`
  1. `FlagRow`: junto al `defaultBadge` (165-167), cuando `isModifiedFromDefault(flag)` renderizar
     `<span className={styles.modifiedBadge}>modificada</span>`.
  2. `renderSection` (316-352): calcular `const modified = catFlags.filter(isModifiedFromDefault).length;`
     y extender el meta (línea 334) a: `` {catFlags.length} flags · {visibleActive} activas{modified > 0 ? ` · ${modified} modificadas` : ""} ``.
  3. Hero (372-385): agregar un cuarto `heroStat` con `flags.filter(isModifiedFromDefault).length` y
     label `fuera de default`.
  4. **[ADICIÓN ARQUITECTO]** Filtro "Solo modificadas": agregar un checkbox junto a "Solo activas"
     (bloque `styles.search`, Panel:409-425) con estado `const [onlyModified, setOnlyModified] = useState(false);`
     y extender `matches()` (Panel:246-254) con, como primera condición junto a `onlyActive`:
     `if (onlyModified && !isModifiedFromDefault(f)) return false;`
     (agregar `onlyModified` a las dependencias del `useMemo` de `orderedSections`, Panel:304, y al
     `open` de las secciones igual que `onlyActive`). Convierte el badge en triage de un click:
     "mostrame solo lo que toqué".
- Editar CSS: `.modifiedBadge` (estilo base de `.defaultBadge`, color distinto de `env`).
- Editar (test PRIMERO): `HarnessFlagsPanel.test.tsx` + crear
  `Stacky Agents/frontend/src/components/__tests__/harnessVisuals.isModified.test.ts`:
  - `test_bool_default_off_value_on_is_modified`
  - `test_default_unknown_never_modified`
  - `test_csv_empty_equals_null_default_not_modified`
  - `test_int_string_vs_number_same_value_not_modified` (ej. default 3, value "3")
  - Panel: `test_section_meta_shows_modified_count`, `test_hero_shows_out_of_default_total`,
    `test_only_modified_filter_hides_default_flags`.

**Comandos:** los mismos de F2 (detección `npx vitest --version` [C4] + `tsc --noEmit`).
**Criterio binario:** `tsc --noEmit` exit 0; tests de `isModifiedFromDefault` verdes si vitest disponible.
**Flag:** ninguna. **Runtimes:** impacto nulo. **Trabajo del operador:** ninguno.

### F4 — Backend + hero: desvío respecto del perfil más cercano

**Objetivo:** que `Perfil: personalizado` diga además el perfil más cercano y cuántas flags difieren.

**Archivos:**
- Editar: `Stacky Agents/backend/services/harness_profiles.py` — agregar función pura:

```python
def profile_deltas() -> dict[str, int]:
    """Para cada perfil en PROFILES, cuántas de SUS keys difieren del valor actual.

    Reusa la misma lectura de valores que detect_profile() (misma normalización).
    Devuelve p.ej. {"off": 3, "safe": 1, "full": 12}. Determinista, sin side effects.
    """
```

  Implementación [C3 — sin hedge, pasos deterministas]:
  1. Leer `services/harness_profiles.py` y localizar cómo `detect_profile()` obtiene el valor actual
     de cada key para compararlo con el perfil.
  2. Extraer esa obtención a un helper módulo-level `_current_value(key: str) -> object` (si un helper
     con ese nombre ya existe, reusarlo sin duplicar). `detect_profile()` DEBE quedar consumiendo
     `_current_value` (refactor sin cambio de comportamiento).
  3. `profile_deltas()` itera `PROFILES[name].items()` y cuenta `1` por cada key cuyo
     `_current_value(key)` difiere del valor esperado, con la MISMA normalización de comparación que
     usa `detect_profile()` (si compara con `==` sobre valores casteados, usar exactamente eso).
  4. Verificar el refactor: localizar los tests existentes de perfiles con
     `grep -rl "detect_profile" "Stacky Agents/backend/tests"` y correr ESOS archivos; deben seguir
     verdes sin modificar sus asserts.
- Editar: `Stacky Agents/backend/api/harness_flags.py:78-83` — agregar al JSON del GET:
  `"profile_deltas": profile_deltas(),` (import junto a `detect_profile`).
- Editar: `Stacky Agents/frontend/src/api/endpoints.ts` — tipo de respuesta del list:
  `profile_deltas?: Record<string, number>;`
- Editar: `HarnessFlagsPanel.tsx:370` — cuando `activeProfile` es null/undefined y hay
  `profile_deltas`, calcular el mínimo: `const nearest = Object.entries(deltas).sort((a,b)=>a[1]-b[1])[0];`
  y renderizar `Perfil: <strong>personalizado</strong> <span className={styles.nearestProfile}>(más cercano: {nearest[0]}, {nearest[1]} diferencia{nearest[1]===1?"":"s"})</span>`.
  Si `activeProfile` tiene valor, comportamiento actual sin cambios.
- Crear (test PRIMERO): `Stacky Agents/backend/tests/test_harness_profile_deltas.py`:
  - `test_deltas_zero_for_applied_profile` — aplicar (monkeypatch de valores) el perfil `off` →
    `profile_deltas()["off"] == 0`.
  - `test_deltas_counts_divergent_keys` — desviar 2 keys del perfil `safe` → `["safe"] == 2`.
  - `test_deltas_keys_match_profiles` — `set(profile_deltas()) == set(PROFILES)`.
  - `test_get_endpoint_includes_profile_deltas` — el GET `/api/harness-flags` incluye la clave
    (mismo harness de app/test client que `tests/test_harness_flags.py`).

**Comandos:**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests\test_harness_profile_deltas.py -q
```
más `npx tsc --noEmit` en frontend.
**Criterio binario:** exit 0 en ambos.
**Flag:** ninguna. **Runtimes:** impacto nulo. **Trabajo del operador:** ninguno.

### F5 — Ratchet: registrar los tests nuevos

**Objetivo:** cumplir la regla del Plan 49 F4 (meta-test de cobertura del arnés).

**Archivos:** los DOS scripts que definen `HARNESS_TEST_FILES` (buscar con
`grep -r "HARNESS_TEST_FILES" "Stacky Agents"` — hay variante `.sh` y `.ps1`).
Agregar: `test_harness_flags_requires.py` y `test_harness_profile_deltas.py`.

**Criterio binario:** el meta-test del ratchet (Plan 49 F4) pasa:
```
.venv\Scripts\python.exe -m pytest tests\test_harness_ratchet.py -q
```
(si el archivo del meta-test tiene otro nombre, localizarlo con `grep -rl "HARNESS_TEST_FILES" tests\`
y correr ESE archivo).
**Flag/Runtimes/Operador:** n/a, ninguno.

## 5. Riesgos y mitigaciones

- **R1: un `requires` mal declarado marca "sin efecto" a una flag que sí funciona.** Mitigación:
  procedimiento de verificación por consumidor en F1 (grep obligatorio) + mapa congelado en test +
  el aviso es informativo (no bloquea nada).
- **R2: falso "modificada" por normalización de tipos.** Mitigación: `isModifiedFromDefault`
  normaliza por tipo con tests de casos borde (bool, csv vacío, int como string).
- **R3: `profile_deltas` duplica lógica de `detect_profile` y divergen.** Mitigación: F4 obliga a
  reusar el mismo helper de lectura; test `test_deltas_zero_for_applied_profile` los mantiene atados.
- **R4: vitest no instalado en el entorno local.** Mitigación declarada en F2/F3: `tsc --noEmit` es el
  gate mínimo, los tests quedan escritos para CI y el reporte final lo dice honestamente.
- **R5: romper `test_default_known_only_for_curated`.** Mitigación: prohibición explícita de tocar
  `default` (guardarraíles + F1 reglas duras + caso de test en F0).

## 6. Fuera de scope

- Cualquier evaluación de `requires` en runtime (runners/gates): sigue siendo solo metadata de UI.
- Presets nuevos o edición de perfiles (off/safe/full quedan como están).
- Historial/auditoría de cambios de flags (quién/cuándo).
- Preview de efecto/costo de una flag ("+8s al inicio"): requeriría telemetría por flag, otro plan.
- Deshabilitar controles de hijas con master OFF (decisión explícita: NO, para permitir preconfigurar).
- Dependencias de profundidad >1 o condiciones compuestas (AND/OR de masters).

## 7. Glosario

- **Arnés (harness):** conjunto de flags/gates/telemetría que gobierna cómo corren los agentes.
- **FlagSpec / FLAG_REGISTRY:** dataclass y tupla módulo-level en
  `Stacky Agents/backend/services/harness_flags.py` que declaran todas las flags del panel.
- **`pair`:** campo existente de FlagSpec que une un bool master con SU csv `*_PROJECTS` para
  renderizarlos juntos (el csv se deshabilita si el bool está OFF).
- **`env_only`:** la flag no es atributo de `Config`; vive en `os.environ` y se lee en call time.
  Igual se edita por UI (el endpoint escribe `.env` y actualiza `os.environ` en caliente).
- **Perfil (off/safe/full):** conjuntos predefinidos de valores en `services/harness_profiles.py`;
  `detect_profile()` devuelve el nombre si el estado actual coincide, o `None` (= "personalizado").
- **Ratchet:** meta-test del Plan 49 que exige que todo archivo de test del arnés esté registrado en
  `HARNESS_TEST_FILES` (scripts sh y ps1).
- **Gotcha de defaults:** `default_is_known` cuenta cualquier `default` no-None contra una lista
  congelada de 12 keys (Plan 63); agregar `default=` a un spec rompe ese test.

## 8. Orden de implementación

1. F0 (backend: campo + funciones puras + serialización, TDD).
2. F1 (poblar mapa con verificación por consumidor + congelamiento).
3. F2 (UI dependencias + badge env).
4. F3 (UI modificada + contadores).
5. F4 (profile_deltas backend + hero).
6. F5 (ratchet).

## 9. Definición de Hecho (DoD)

- [ ] `test_harness_flags_requires.py` y `test_harness_profile_deltas.py` verdes con el venv del repo.
- [ ] `tests/test_harness_flags.py` (existente) sigue verde sin modificaciones de asserts previos.
- [ ] `test_default_known_only_for_curated` sigue verde (ningún default nuevo).
- [ ] `npx tsc --noEmit` exit 0 en frontend; tests de Panel/visuals escritos (verdes si
      `npx vitest --version` exit 0; si no, reporte honesto "no ejecutados").
- [ ] Cada fila del panel muestra la key técnica (`flag.key`) y existe el filtro "Solo modificadas".
- [ ] El GET `/api/harness-flags` incluye `requires`, `requires_met` por flag y `profile_deltas` global.
- [ ] Hija con master OFF muestra "Sin efecto: requiere ... activada" y su control sigue editable.
- [ ] Ratchet verde con los 2 archivos de test registrados (sh + ps1).
- [ ] Cero cambios en runners/gates/prompts: `git diff` no toca `*_runner.py`, `harness/` de runtime,
      ni prompts de agentes.
