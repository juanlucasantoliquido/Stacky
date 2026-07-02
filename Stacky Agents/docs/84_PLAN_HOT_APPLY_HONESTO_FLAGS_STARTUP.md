# Plan 84 — Aplicación en caliente honesta: flags de startup del arnés (`restart_required` + "pendiente de reinicio")

**Estado:** PROPUESTO v2 (2026-07-02) — v1 → v2 tras crítica adversarial (`criticar-y-mejorar-plan`)

### Changelog v1 → v2
- **C1:** el refactor de `read_current()` a `_current_value()` NO es byte-idéntico: para flags
  `type="str"` env_only sin configurar, el bloque inline actual devuelve `0` (no contempla `"str"`,
  harness_flags.py:1936-1942) y `_type_zero` devuelve `""`. Se declara como CORRECCIÓN deliberada
  (el zero de un str es `""`) con test explícito `test_read_current_str_env_only_unset_is_empty_string`.
- **C2:** los tests del PUT (F2) monkeypatchean OBLIGATORIAMENTE
  `api.harness_flags._ENV_PATH` a `tmp_path / ".env"` (el módulo lo prevé, api/harness_flags.py:23);
  sin eso escribirían el `.env` vivo del repo.
- **C3:** eliminado el hedge "localizar y correr ESE archivo": comando determinista que corre TODOS
  los archivos que devuelva `grep -rl "read_current" tests`.
- **C4:** receta literal para `test_snapshot_boot_values_captures_only_restart_required` en F0 con
  registry sintético (`monkeypatch.setattr(harness_flags, "FLAG_REGISTRY", (...))`), sin depender de F1.
- **C5:** documentado el escape hatch del centinela de F1: una lectura call-time legítima nueva en
  `app.py` se resuelve moviéndola a un módulo de servicio, o declarando `restart_required=True` tras
  auditar que es consumo boot-time.
- **C6:** F3.4 determinista: grep del handler del PUT en el Panel; si no refetchea tras PUT, agregar
  la llamada al loader existente.
- **[ADICIÓN ARQUITECTO v2]:** `read_current()` serializa `boot_value` (solo con valor cuando
  `pending_restart` es true, si no `null`) y la nota de fila muestra
  "el proceso corre con `<boot_value>`": el operador ve exactamente qué valor está ACTIVO versus
  qué guardó. Con tests en F0 y F3.

## 1. Objetivo e impacto

El PUT `/api/harness-flags` hace hot-apply REAL: persiste al `.env`, actualiza `os.environ`
(`Stacky Agents/backend/api/harness_flags.py:63-68`) y pisa el atributo del singleton `config` con
`setattr` (`api/harness_flags.py:159-163`; `config = Config()` es instancia, `config.py:887`). Los
consumidores que leen `config.STACKY_X`/`os.getenv` en call-time ven el cambio al instante — se
verificó por grep que NO existe ningún módulo que congele una flag del registry en una constante de
import-time.

**EXCEPCIÓN verificada:** 4 flags del panel se consumen UNA sola vez dentro de `create_app()` para
decidir si arrancan daemons de fondo, y capturan el intervalo en una variable local del closure:

| Key | Consumo boot-time | Spec en registry | `env_only` |
|---|---|---|---|
| `STACKY_DIGEST_INTERVAL_HOURS` | `app.py:366-367` (gate + `interval_seconds`) | harness_flags.py:547 | False (config.py:328) |
| `STACKY_MEMORY_REVIEW_SWEEP_HOURS` | `app.py:386-387` (gate + `_review_sweep_seconds`) | harness_flags.py:358 | False (config.py:257) |
| `STACKY_ADO_EDIT_LEARNING_ENABLED` | `app.py:410-413` (gate del daemon plan 60) | harness_flags.py:1700 | True |
| `STACKY_ADO_EDIT_SWEEP_HOURS` | `app.py:414` (`_ado_edit_seconds`) | harness_flags.py:1711 | True |

Para estas 4, el PUT responde `{ok, applied}` (`api/harness_flags.py:167`) = **éxito FALSO**: el
cambio queda persistido pero es inerte hasta reiniciar el backend. Peor caso 0→ON: el hilo nunca se
creó al boot, así que "prender" desde la UI no arranca NADA. Caso crítico real:
`STACKY_ADO_EDIT_LEARNING_ENABLED` es el master del aprendizaje bidireccional (planes 60/81) — el
operador lo activa desde el panel y el loop de aprendizaje queda muerto en silencio.

**Propuesta:** metadata aditiva `restart_required: bool` en `FlagSpec` (mapa curado y CONGELADO por
test, mismo patrón que `requires` del Plan 82 F1 y `min_value/max_value` del Plan 83 F1) + snapshot
de los valores boot-time tomado en `create_app()` + campo `pending_restart` calculado en
`read_current()` (valor actual ≠ valor con el que arrancó el proceso) + el PUT devuelve
`restart_required_keys` + UI: badge "reinicio" en la fila, nota "pendiente de reinicio" y chip de
triage en el hero.

**KPI/impacto esperado:**
- 0 PUTs falsamente exitosos sin aviso: todo cambio a una flag de startup devuelve
  `restart_required_keys` y la fila muestra "pendiente de reinicio del backend".
- El operador distingue de un vistazo qué flags aplican en caliente (todas menos 4) y cuáles no.
- Impacto runtime NULO: ningún runner/gate/daemon lee los símbolos nuevos; los loops de `app.py`
  NO se tocan.

## 2. Por qué ahora / gap que cierra

Los planes 82 (PROPUESTO v3: `requires`, badge `env`, deltas de perfil) y 83 (PROPUESTO v3: bounds
numéricos) cierran relaciones, origen, desvío y validez del valor. Ninguno cubre la **vigencia**
del valor: ¿el proceso que corre está usando lo que dice el panel? Para 4 flags la respuesta puede
ser NO y hoy es indetectable desde la UI. Es la última clase de "flag muerta silenciosa" del panel
(se auditó: no hay constantes import-time; `STACKY_MAX_CONCURRENT_RUNS` se lee call-time en
`services/run_slots.py:23`; el resto de consumidores lee `config.X`/`os.getenv` por llamada). Reusa
el patrón ya probado: campo aditivo en `FlagSpec` + mapa curado congelado + serialización en
`read_current()` + presentación en `FlagRow`.

## 3. Principios y guardarraíles (no negociables)

- **Paridad 3 runtimes (Codex CLI / Claude Code CLI / GitHub Copilot Pro):** impacto NULO en los
  tres. Los símbolos nuevos solo los evalúan `read_current()` (GET del panel), el PUT y el TSX.
  Ningún runner los importa. No hay rama de comportamiento nueva en tiempo de run.
- **NO cambiar el comportamiento de los loops (fuera de scope explícito):** prohibido re-leer config
  por iteración, arrancar/parar hilos en caliente o tocar `_digest_loop`/`_memory_review_sweep_loop`/
  `_ado_edit_sweep_loop`. Este plan es metadata + presentación honesta; la mecánica de reinicio
  sigue siendo humana (human-in-the-loop).
- **Cero trabajo extra al operador:** todo informativo/automático. Los controles NUNCA se bloquean;
  el PUT sigue aceptando y persistiendo el cambio (sobrevive al reinicio vía `.env`, que es
  exactamente lo deseado). Solo se informa.
- **Sin flag de comportamiento nueva:** mismo precedente que 62/63/78/82/83 (cambio de panel/metadata
  sin flag). Rollback = revertir el commit.
- **Gotcha de defaults (regla dura):** NINGÚN `FlagSpec` se toca en su campo `default`. El campo
  nuevo `restart_required` es aditivo con default `False`. Prohibido pasar
  `default=False`/`default=True`/`default=<n>` a specs existentes o nuevos (rompería
  `test_default_known_only_for_curated`, lista congelada Plan 63).
- **Fail-open:** si el snapshot boot-time no existe (tests unitarios que no llaman `create_app`,
  import directo del módulo), `pending_restart` es `False`. Nunca un error, nunca un aviso falso.
- **Mono-operador / sin auth:** sin cambios.
- **Backward-compatible:** `restart_required=False` en todos los specs no listados; el GET agrega
  claves nuevas sin quitar ninguna; el frontend tolera ausencia (`?? false`).
- **Convivencia con planes 82 y 83 (NO implementados aún):** los tres planes agregan campos a
  `FlagSpec`, claves al payload de `read_current()` y presentación a `FlagRow`. Son independientes y
  conmutativos: este plan referencia SÍMBOLOS (no números de línea absolutos) en los puntos que
  82/83 desplazan. El campo nuevo va al FINAL de `FlagSpec` (después del último campo existente al
  momento de implementar: `default`, o `requires`/`min_value`/`max_value` si 82/83 ya entraron).

## 4. Fases

### F0 — Campo `restart_required` en FlagSpec + snapshot boot + `pending_restart` (backend, TDD)

**Objetivo:** que el registry declare "esta flag solo se lee al arrancar el proceso" y que el GET
pueda decir si el valor actual difiere del que usó el boot.

**Archivos:**
- Editar: `Stacky Agents/backend/services/harness_flags.py`
- Editar: `Stacky Agents/backend/app.py` (1 línea dentro de `create_app`, ver [4])
- Crear (test PRIMERO): `Stacky Agents/backend/tests/test_harness_flags_restart_required.py`

**Cambios exactos:**

1. En `FlagSpec` (harness_flags.py:19-27) agregar UN campo al final (después del último campo
   existente en el momento de implementar):

```python
    restart_required: bool = False  # Plan 84 — True = la flag se consume UNA vez en
                                    # create_app (arranque de daemons); un cambio por UI
                                    # persiste pero NO aplica hasta reiniciar el backend.
                                    # Solo informativo para la UI; ningún runner lo evalúa.
```

2. Agregar al final del módulo (antes de `read_current`) el snapshot boot y dos funciones puras:

```python
# Plan 84 — snapshot de los valores boot-time de las flags restart_required.
# Lo llena create_app() vía snapshot_boot_values(). Vacío = fail-open (tests).
_BOOT_VALUES: dict[str, object] = {}


def _current_value(spec: FlagSpec) -> object:
    """Valor vigente de la flag: os.getenv casteado (env_only) o atributo de config."""
    if spec.env_only:
        raw = os.getenv(spec.key)
        if raw is None:
            return _type_zero(spec.type)
        return _cast(spec, raw)
    from config import config
    return getattr(config, spec.key)


def snapshot_boot_values() -> None:
    """Captura el valor boot-time de cada flag restart_required. Idempotente NO:
    pisa siempre (create_app la llama UNA vez, al principio, antes de armar daemons)."""
    _BOOT_VALUES.clear()
    for spec in FLAG_REGISTRY:
        if spec.restart_required:
            _BOOT_VALUES[spec.key] = _current_value(spec)


def pending_restart(spec: FlagSpec, value: object) -> bool:
    """True si la flag es restart_required, hay snapshot, y el valor actual difiere
    del valor con el que arrancó el proceso. Fail-open: sin snapshot → False."""
    if not spec.restart_required:
        return False
    if spec.key not in _BOOT_VALUES:
        return False
    return value != _BOOT_VALUES[spec.key]
```

   Nota (C1-v2): `read_current()` hoy calcula el valor con un bloque inline (harness_flags.py:1934-1946)
   que NO contempla `type="str"`: una flag str env_only sin configurar cae al else y devuelve `0`.
   `_current_value` usa `_type_zero`, que devuelve `""` para str. Refactorizar `read_current()` para
   llamar `value = _current_value(spec)` — es un delta DELIBERADO y correcto solo para ese caso
   (str env_only sin configurar: `0` → `""`); para bool/int/float/csv/json el comportamiento es
   byte-idéntico. Cubierto por el test `test_read_current_str_env_only_unset_is_empty_string` (abajo).

3. En el dict que arma `read_current()` (harness_flags.py:1948-1961) agregar TRES claves al final
   ([ADICIÓN ARQUITECTO v2] `boot_value`):

```python
            "restart_required": spec.restart_required,
            "pending_restart": pending_restart(spec, value),
            "boot_value": (_BOOT_VALUES.get(spec.key)
                           if pending_restart(spec, value) else None),
```

   `boot_value` solo lleva valor cuando hay un cambio pendiente (si no, `null`): la UI puede decir
   "el proceso corre con `<boot_value>`" sin ambigüedad y sin ensanchar el payload en el caso común.

4. En `app.py`, dentro de `create_app()`, ANTES del bloque del digest daemon (hoy `app.py:364`),
   agregar:

```python
    # Plan 84 — snapshot boot-time para "pendiente de reinicio" del panel de flags.
    from services.harness_flags import snapshot_boot_values
    snapshot_boot_values()
```

**Tests (escribir PRIMERO, en `test_harness_flags_restart_required.py`):**
- `test_flagspec_restart_required_default_false` — un `FlagSpec` mínimo sin el kwarg tiene
  `restart_required is False`.
- `test_pending_restart_false_without_snapshot` — con `_BOOT_VALUES` vacío
  (`monkeypatch.setattr(harness_flags, "_BOOT_VALUES", {}, raising=True)` o `.clear()`),
  `pending_restart(spec_restart_required, 5) is False` (fail-open).
- `test_pending_restart_true_when_value_differs` — sembrar `_BOOT_VALUES[key] = 0` vía
  `monkeypatch.setitem`, spec sintético `restart_required=True`; `pending_restart(spec, 6) is True`
  y `pending_restart(spec, 0) is False`.
- `test_pending_restart_false_for_normal_flag` — spec con `restart_required=False` devuelve False
  aunque haya snapshot con valor distinto.
- `test_snapshot_boot_values_captures_only_restart_required` — (C4-v2, receta literal) construir
  DOS specs sintéticos `spec_a = FlagSpec(key="STACKY_TEST_A", type="int", label="", description="",
  group="global", env_only=True, restart_required=True)` y `spec_b = FlagSpec(key="STACKY_TEST_B",
  type="int", label="", description="", group="global", env_only=True)`; parchear
  `monkeypatch.setattr(harness_flags, "FLAG_REGISTRY", (spec_a, spec_b))`; tras
  `snapshot_boot_values()`, `set(harness_flags._BOOT_VALUES) == {"STACKY_TEST_A"}`.
- `test_read_current_serializes_restart_fields` — todo item del GET tiene las claves
  `restart_required` (bool), `pending_restart` (bool) y `boot_value` (None cuando no hay pendiente).
- `test_read_current_pending_restart_reflects_env_change` — para
  `STACKY_ADO_EDIT_SWEEP_HOURS` (env_only): snapshot con env sin setear (boot=0/`_type_zero`),
  luego `monkeypatch.setenv("STACKY_ADO_EDIT_SWEEP_HOURS", "12")` → el item del GET tiene
  `pending_restart is True` y `boot_value == 0`.
- `test_read_current_str_env_only_unset_is_empty_string` — (C1-v2) para una flag `type="str"`
  env_only del registry (localizarla con `grep -n 'type="str"' services/harness_flags.py`) con la
  env var sin setear (`monkeypatch.delenv(key, raising=False)`), el item del GET tiene
  `value == ""` (antes del refactor devolvía `0`; delta deliberado documentado en el Changelog).

**Comando:** `cd "Stacky Agents/backend"` y
`.venv\Scripts\python.exe -m pytest tests\test_harness_flags_restart_required.py -q`

**Criterio binario:** los 8 tests pasan Y los tests existentes del panel siguen verdes. Comando
determinista (C3-v2), desde `Stacky Agents/backend`:
`grep -rl "read_current" tests | %{ .venv\Scripts\python.exe -m pytest $_ -q }` (PowerShell) o
`for f in $(grep -rl "read_current" tests); do .venv/Scripts/python.exe -m pytest "$f" -q; done`
(bash) — TODOS los archivos que devuelva el grep deben terminar verdes.

**Flag:** ninguna (metadata + GET; sin rama de comportamiento).
**Runtimes:** impacto nulo en los 3 (ningún runner importa estos símbolos).
**Trabajo del operador:** ninguno.

### F1 — Mapa curado CONGELADO de flags restart_required (backend, TDD)

**Objetivo:** marcar exactamente las 4 flags verificadas y congelar la lista por test para que nadie
agregue una quinta sin evidencia (mismo patrón que Plan 82 F1 / Plan 83 F1).

**Archivos:**
- Editar: `Stacky Agents/backend/services/harness_flags.py` (los 4 `FlagSpec`)
- Editar: `Stacky Agents/backend/tests/test_harness_flags_restart_required.py`

**Cambios exactos:**

1. Agregar `restart_required=True` (SOLO ese kwarg; prohibido tocar `default`) a los 4 specs:
   - `STACKY_DIGEST_INTERVAL_HOURS` (spec en harness_flags.py, buscar `key="STACKY_DIGEST_INTERVAL_HOURS"`)
   - `STACKY_MEMORY_REVIEW_SWEEP_HOURS`
   - `STACKY_ADO_EDIT_LEARNING_ENABLED`
   - `STACKY_ADO_EDIT_SWEEP_HOURS`

2. Test de congelamiento (con la receta de auditoría como comentario, para futuros planes):

```python
# Receta de auditoría (determinista) para decidir si una flag es restart_required:
# grep -n 'config\.STACKY_\|os\.environ\.get("STACKY_\|os\.getenv("STACKY_' backend/app.py
# → toda key del registry consumida dentro de create_app() (gate o intervalo de un
#   daemon) es restart_required. Cualquier otra key NO lo es (se lee call-time).
_EXPECTED_RESTART_REQUIRED = frozenset({
    "STACKY_DIGEST_INTERVAL_HOURS",
    "STACKY_MEMORY_REVIEW_SWEEP_HOURS",
    "STACKY_ADO_EDIT_LEARNING_ENABLED",
    "STACKY_ADO_EDIT_SWEEP_HOURS",
})


def test_restart_required_map_is_frozen():
    actual = {s.key for s in FLAG_REGISTRY if s.restart_required}
    assert actual == _EXPECTED_RESTART_REQUIRED
```

3. Test centinela anti-drift de `app.py` (que el mapa no quede stale si alguien agrega un daemon):

```python
def test_app_startup_flag_reads_are_all_declared():
    """Toda key STACKY_* del registry leída en app.py debe estar en el mapa congelado."""
    import re
    from pathlib import Path
    src = (Path(__file__).parent.parent / "app.py").read_text(encoding="utf-8")
    keys_in_app = set(re.findall(r'(?:config\.|environ\.get\(\"|getenv\(\")(STACKY_[A-Z_]+)', src))
    registry_keys = {s.key for s in FLAG_REGISTRY}
    startup_reads = keys_in_app & registry_keys
    assert startup_reads <= _EXPECTED_RESTART_REQUIRED, (
        f"Flags del registry leídas en app.py sin declarar restart_required: "
        f"{sorted(startup_reads - _EXPECTED_RESTART_REQUIRED)}"
    )
```

   Escape hatch documentado (C5-v2, dejar como comentario junto al test): si en el futuro `app.py`
   necesita leer una key del registry en CALL-TIME (no boot), hay exactamente DOS salidas válidas —
   (a) mover esa lectura a un módulo de servicio (preferida), o (b) si la auditoría confirma que es
   consumo boot-time, declararla `restart_required=True` y agregarla al mapa congelado. Prohibido
   agregar excepciones al regex.

4. Verificar y NO romper: `test_default_known_only_for_curated` (correr el archivo que lo contiene,
   localizarlo con `grep -rl "default_known_only_for_curated" tests\`).

**Comando:** `.venv\Scripts\python.exe -m pytest tests\test_harness_flags_restart_required.py -q`

**Criterio binario:** mapa congelado verde + centinela de app.py verde + el test curado del Plan 63
sigue verde.

**Flag:** ninguna. **Runtimes:** impacto nulo. **Trabajo del operador:** ninguno.

### F2 — PUT honesto: `restart_required_keys` en la respuesta (backend, TDD)

**Objetivo:** que el PUT deje de afirmar éxito pleno cuando parte del cambio no aplica en caliente.

**Archivos:**
- Editar: `Stacky Agents/backend/api/harness_flags.py` (`put_harness_flags`)
- Crear o extender: `Stacky Agents/backend/tests/test_harness_flags_endpoint_restart.py`

**Cambios exactos:** en `put_harness_flags`, después del hot-apply (hoy `api/harness_flags.py:154-163`)
y antes del `return`:

```python
    restart_keys = sorted(
        k for k in typed if _REGISTRY_INDEX[k].restart_required
    )
    ...
    return jsonify({"ok": True, "applied": typed, "restart_required_keys": restart_keys})
```

La clave `restart_required_keys` va SIEMPRE en la respuesta (lista vacía si no aplica): contrato
estable, el frontend no necesita `in`.

**Tests (`test_harness_flags_endpoint_restart.py`, patrón del test client Flask existente —
espejar el setup de los tests del endpoint actuales, localizados con
`grep -rl "put_harness_flags\|harness-flags" tests\`). REGLA DURA (C2-v2): TODO test que haga PUT
debe monkeypatchear `monkeypatch.setattr(api.harness_flags, "_ENV_PATH", tmp_path / ".env")`
(el módulo lo prevé para tests, api/harness_flags.py:23); sin eso el test ESCRIBE el `.env` vivo
del repo. Verificar además que los tests no dejen residuos en `os.environ`
(`monkeypatch.delenv` en teardown implícito de monkeypatch):**
- `test_put_normal_flag_returns_empty_restart_keys` — PUT de una flag no-startup (p. ej.
  `STACKY_MAX_CONCURRENT_RUNS`) → `restart_required_keys == []`.
- `test_put_startup_flag_returns_key` — PUT de `STACKY_DIGEST_INTERVAL_HOURS=2` →
  `restart_required_keys == ["STACKY_DIGEST_INTERVAL_HOURS"]` y `ok is True` (el cambio SÍ se
  persiste; solo se informa).
- `test_put_mixed_returns_only_startup_keys` — PUT con una de cada → solo la startup en la lista.

**Comando:** `.venv\Scripts\python.exe -m pytest tests\test_harness_flags_endpoint_restart.py -q`

**Criterio binario:** 3 tests verdes + los tests existentes del endpoint siguen verdes.

**Flag:** ninguna. **Runtimes:** impacto nulo. **Trabajo del operador:** ninguno.

### F3 — UI: badge "reinicio", nota "pendiente de reinicio" y chip en el hero (frontend)

**Objetivo:** que el operador VEA la semántica: qué flags no aplican en caliente y cuáles tienen un
cambio pendiente ahora mismo.

**Archivos:**
- Editar: `Stacky Agents/frontend/src/components/HarnessFlagsPanel.tsx`
- Editar (si el tipo vive ahí): el tipo del flag en `endpoints.ts`/tipos del panel (localizar con
  `grep -rn "env_only" frontend/src` y espejar cómo viaja `env_only`).

**Cambios exactos:**

1. Tipo: agregar `restart_required?: boolean`, `pending_restart?: boolean` y
   `boot_value?: string | number | boolean | null` al tipo del flag (tolerar ausencia: leer con
   `?? false` / `?? null`).
2. `FlagRow`: junto a los badges existentes (patrón del badge `def:`, Panel:165-167 hoy), si
   `flag.restart_required` renderizar badge `reinicio` con
   `title="Esta flag se lee al arrancar el backend; los cambios aplican tras reiniciar"`.
3. `FlagRow`: si `flag.pending_restart` renderizar nota bajo el control (mismo estilo visual que
   las notas de fila de los planes 82/83 si ya existen; si no, un `<div className={styles.rowNote}>`
   nuevo). Texto exacto ([ADICIÓN ARQUITECTO v2], usa `boot_value` del GET):
   `Cambio pendiente de reinicio del backend — el proceso corre con <boot_value>` (formatear
   `boot_value` con `String(...)`; si `boot_value` es `null` por carrera, omitir el sufijo " — el
   proceso corre con ...").
4. Tras un PUT exitoso, si `restart_required_keys.length > 0`, mostrar el aviso no-bloqueante que el
   panel ya use para feedback (espejar el mecanismo de `apiError`/mensajes del Panel — localizar con
   `grep -n "apiError" HarnessFlagsPanel.tsx`): texto
   `Guardado. Requiere reiniciar el backend: <keys separadas por coma>`. Refetch (C6-v2, paso
   determinista): localizar el handler del PUT en el Panel con `grep -n "update(" HarnessFlagsPanel.tsx`
   (o el nombre del método de `endpoints.ts` que haga el PUT); verificar que tras el PUT se llama al
   loader del GET (la función que puebla `flags`); si NO lo hace, agregar esa llamada reusando el
   loader existente (sin crear fetch nuevo).
5. Hero: chip `N pendientes de reinicio` renderizado SOLO si `N > 0`
   (`N = flags.filter(f => f.pending_restart).length`), mismo patrón visual que el chip
   "N fuera de rango" del Plan 83 si ya existe; al click activa un filtro `onlyPendingRestart`
   (espejo del filtro "Solo activas" existente). Si el Plan 83 no está implementado, el chip se
   agrega igual con el patrón de stats del hero (`.heroStats`).

**Tests:** detección determinista de vitest: `npx vitest --version` (exit 0 → escribir/correr tests
de componente para: badge presente cuando `restart_required`, nota cuando `pending_restart`, chip
solo si N>0; exit ≠0 → degradar a `npx tsc --noEmit` y REPORTARLO como "tests de componente no
corridos", sin marcar verde).

**Comando:** `cd "Stacky Agents/frontend"` y `npx tsc --noEmit` (siempre) + vitest si disponible.

**Criterio binario:** `tsc --noEmit` exit 0; con vitest disponible, los tests del componente verdes.

**Flag:** ninguna. **Runtimes:** impacto nulo (solo panel). **Trabajo del operador:** ninguno.

### F4 — Ratchet: registrar los tests nuevos (backend)

**Objetivo:** que los tests nuevos queden en la lista congelada del arnés (Plan 49 F4).

**Archivos:** los DOS scripts que definen `HARNESS_TEST_FILES` (localizar con
`grep -r "HARNESS_TEST_FILES" "Stacky Agents"` — hay variante `.sh` y `.ps1`). Agregar
`test_harness_flags_restart_required.py` y `test_harness_flags_endpoint_restart.py` a ambos.

**Criterio binario:** el meta-test del ratchet pasa (localizar con
`grep -rl "HARNESS_TEST_FILES" tests\` y correr ESE archivo con
`.venv\Scripts\python.exe -m pytest <archivo> -q`).

**Flag:** ninguna. **Runtimes:** impacto nulo. **Trabajo del operador:** ninguno.

## 5. Riesgos y mitigaciones

- **R1 — Falso "pendiente de reinicio" en tests/import parcial:** mitigado por fail-open
  (`_BOOT_VALUES` vacío → `pending_restart=False`) + test explícito.
- **R2 — Snapshot tomado DESPUÉS de un cambio (orden en create_app):** `snapshot_boot_values()` se
  llama al principio del bloque de daemons, antes de leer las flags para armar hilos; el snapshot y
  la lectura de los daemons ocurren en el mismo boot sin PUTs intercalados (el server aún no
  atiende requests). Riesgo nulo en la práctica; el test de F0 cubre la semántica.
- **R3 — Drift del mapa curado (nuevo daemon sin declarar):** centinela
  `test_app_startup_flag_reads_are_all_declared` (F1) — regex sobre `app.py` cruzada con el
  registry; falla si aparece una lectura startup no declarada.
- **R4 — Colisión textual con planes 82/83 no implementados:** los tres planes agregan campos/claves
  aditivas en los mismos puntos; este plan referencia símbolos, no líneas. Orden de campos: al final
  de `FlagSpec`. Conmutativo.
- **R5 — `!=` entre tipos (bool vs int) en `pending_restart`:** el snapshot y el valor actual salen
  de la MISMA función `_current_value` (mismo cast); comparación homogénea por construcción.

## 6. Fuera de scope

- Re-leer config por iteración en los daemons, o arrancar/parar hilos en caliente (cambio de
  comportamiento runtime; expresamente prohibido en este plan).
- Reinicio del backend desde la UI (botón "reiniciar"): decisión de operación, no de claridad.
- Bounds (Plan 83), `requires`/badge env/deltas (Plan 82): planes independientes.
- Cualquier flag fuera de las 4 verificadas (la receta de auditoría queda documentada en F1).

## 7. Glosario

- **Flag de startup / `restart_required`:** flag del registry que `create_app()` lee UNA sola vez
  para decidir si arranca un daemon de fondo y con qué intervalo; los cambios por UI persisten al
  `.env` pero no afectan al proceso vivo.
- **`pending_restart`:** el valor actual (env/config) difiere del valor snapshot tomado al boot →
  hay un cambio guardado que el proceso vivo todavía no usa.
- **Hot-apply:** el PUT del panel escribe `.env`, `os.environ` y `setattr(config, ...)`; efectivo
  para todo consumo call-time.
- **Ratchet (`HARNESS_TEST_FILES`):** lista congelada de archivos de test del arnés (Plan 49); todo
  test nuevo del arnés debe registrarse o el meta-test falla.
- **Gotcha de defaults:** `default_is_known` cuenta cualquier `default` no-None contra una lista
  congelada de 12 keys (Plan 63); por eso NINGÚN spec nuevo/editado pasa `default=`.

## 8. Orden de implementación

1. F0 (campo + snapshot + `pending_restart` + serialización, TDD).
2. F1 (mapa curado congelado + centinela app.py).
3. F2 (PUT honesto).
4. F3 (UI badge/nota/chip).
5. F4 (ratchet).

## 9. Definición de Hecho (DoD)

- [ ] `FlagSpec.restart_required` existe, default `False`; NINGÚN spec cambió su campo `default`;
      `test_default_known_only_for_curated` verde.
- [ ] Las 4 keys verificadas (y SOLO esas) tienen `restart_required=True`; mapa congelado + centinela
      de `app.py` verdes.
- [ ] `read_current()` serializa `restart_required`, `pending_restart` y `boot_value` (fail-open
      sin snapshot); `create_app()` llama `snapshot_boot_values()`; el delta str-env_only-unset
      (`0`→`""`) está cubierto por test.
- [ ] Los tests del endpoint monkeypatchean `_ENV_PATH` (jamás escriben el `.env` vivo).
- [ ] El PUT devuelve `restart_required_keys` (lista, siempre presente) y sigue persistiendo el
      cambio (nunca bloquea).
- [ ] UI: badge "reinicio" por fila, nota "Cambio pendiente de reinicio del backend", aviso post-PUT
      y chip en hero solo si N>0; `tsc --noEmit` exit 0; vitest corrido o degradación reportada.
- [ ] Tests nuevos registrados en `HARNESS_TEST_FILES` (sh y ps1); meta-test del ratchet verde.
- [ ] Cero cambios en `_digest_loop`/`_memory_review_sweep_loop`/`_ado_edit_sweep_loop` y en los 3
      runtimes.
