# Plan 85 — Cableado honesto del registry de flags: fin de las perillas placebo

**Versión:** v1 (implementado 2026-07-04)
**Estado:** IMPLEMENTADO — supervisado 2026-07-04 ✅ APROBADO
**Supervisión:** 2026-07-04 — 5/5 tests verdes. Centinela detecta 4 flags placebo → marcadas reserved=True. Excluida harness_flags_help.py del corpus. Ledger.json ✅ APROBADO (commit 712b1eb0).
**Dependencias:** ninguna dura. Complementa (no depende de) los planes 82 (relaciones/origen), 83 (validez del valor) y 84 (vigencia/restart). Los campos que agrega a `FlagSpec` son aditivos y no colisionan con `requires` (82) ni `min_value`/`max_value` (83) ni `restart_required` (84).

---

## 1. Objetivo y KPI

**Objetivo.** Que TODA flag que el operador ve en el panel del arnés esté garantizadamente conectada a código productivo que la lee, o esté marcada explícitamente como **reservada** (declarada para una fase diferida que aún no existe) con un badge visible en la UI. Hoy el panel muestra al menos 4 perillas placebo: el operador las togglea y **no pasa absolutamente nada**.

**Evidencia verificada (2026-07-02).** 4 keys de `FLAG_REGISTRY` (`Stacky Agents/backend/services/harness_flags.py`) sin NINGÚN consumidor en código productivo (backend completo excluyendo el registry y `backend/tests/`, frontend `src/`, y sin construcción dinámica parcial del nombre):

| Key | Spec (línea aprox.) | Origen del hueco |
|---|---|---|
| `STACKY_RUN_ADVISOR_ENFORCE` | harness_flags.py:587 | Plan 22 V2.2 (enforce) declarado, nunca implementado. La hermana `STACKY_RUN_ADVISOR_ENABLED` SÍ vive (harness_profiles.py:54). |
| `STACKY_BUDGET_PER_TICKET_USD` | harness_flags.py:598 | Plan 22 V2.2 (budget) declarado, nunca implementado. **Peor caso:** promete un tope de costo (402, degradación de modelo) que NO existe → falsa sensación de guard de presupuesto. |
| `STACKY_BRIEF_MODEL_SELECT_ENABLED` | harness_flags.py:1276 | Plan 42 F3; superseded por Plan 43 (selector model/effort quedó SIEMPRE activo, sin gate). La descripción promete un gate que no existe. |
| `STACKY_SPECULATIVE_MODE` | harness_flags.py:1654 | Plan 57: v1 solo opera modo `eager`; la lectura del modo quedó diferida a v1.1. |

`test_every_registry_flag_is_categorized` (`backend/tests/test_harness_flags.py:478`) valida categoría, **no consumo**. No existe ningún test que impida registrar una flag sin cablearla.

**KPI/impacto:**
- 0 flags placebo silenciosas: toda key del registry o está cableada o luce badge "reservada" con razón.
- Centinela mecánico en CI: registrar una flag nueva sin consumidor rompe el build (a propósito), igual que el patrón de `test_every_registry_flag_is_categorized` (Plan 63).
- Anti-deriva bidireccional: si alguien cablea una flag reservada, el test lo obliga a quitarle la marca (no puede quedar "reservada" y viva a la vez).

**Dimensión que cierra.** 82 = relaciones/origen/desvío; 83 = validez del valor; 84 = vigencia temporal. Este plan cierra la 4ª dimensión: **efectividad/cableado** ("¿esta perilla está conectada a algo?"). Con 82+83+84 implementados, las 4 placebo seguirían invisibles.

---

## 2. Por qué ahora

- La iteración de "claridad de configuración" (planes 82/83/84) declaró el tema agotado; la verificación adversarial de agotamiento encontró este ángulo con evidencia dura.
- El registry creció a ~139 keys (Planes 22→84). El patrón "declaro la flag en la fase de flags, cableo en la fase siguiente" (V2.2, 57-F2a) deja huérfanas cuando la fase siguiente se difiere — y nada lo detecta.
- Costo mínimo: metadata declarativa + 1 test + 1 badge. Impacto runtime **cero**.

---

## 3. Principios y guardarraíles (no negociables)

1. **Cero trabajo extra al operador.** Todo es automático: el badge aparece solo, no hay nueva config que setear. No se agrega ninguna flag nueva (agregar una flag para vigilar flags sería irónico); el cambio es metadata + test + presentación, sin efecto en runtime.
2. **3 runtimes con paridad.** Este plan NO toca el camino de ejecución de ningún runtime (Codex CLI, Claude Code CLI, GitHub Copilot Pro). Los cambios viven en el registry declarativo, un test y el panel React. Impacto por runtime: nulo e idéntico en los tres. No requiere fallback.
3. **Human-in-the-loop.** No se borra ninguna flag ni se deshabilita su edición: el operador conserva todas las perillas; solo se le dice la verdad sobre cuáles no tienen efecto todavía.
4. **Mono-operador, sin auth.** Sin cambios de superficie de seguridad.
5. **Backward-compatible.** Campos nuevos de `FlagSpec` con default (`reserved=False`, `reserved_reason=""`): las 135 flags restantes no se tocan. El JSON del GET solo AGREGA claves. `.env` existentes siguen funcionando igual (las 4 reservadas siguen siendo grabables/legibles; simplemente se documenta que hoy nadie las lee).
6. **Gotcha Plan 63:** NO tocar el campo `default` de ninguna spec ni pasar `default=` en specs existentes (rompería `test_default_known_only_for_curated`). Este plan no modifica `default` en ningún lado.

---

## 4. Fases

### F0 — Test centinela de cableado (TDD: rojo primero)

**Objetivo (1 frase):** un test mecánico que verifique que toda key no-reservada de `FLAG_REGISTRY` aparece como literal en código productivo, y que hoy FALLA exactamente con las 4 keys de la tabla.

**Archivo a crear:** `Stacky Agents/backend/tests/test_flag_wiring.py`

**Contenido exacto (pseudocódigo estricto):**

```python
"""Plan 85 — Centinela de cableado: ninguna flag placebo silenciosa.

Regla: toda key de FLAG_REGISTRY debe aparecer como literal en código
productivo fuera del registry, O estar declarada reserved=True (fase
diferida) con razón. Lista de reservadas CONGELADA: agregar una reservada
nueva exige editar este test a propósito (patrón Plan 61/63).
"""
from pathlib import Path
import pytest

from services.harness_flags import FLAG_REGISTRY

BACKEND_ROOT = Path(__file__).resolve().parent.parent          # .../backend
FRONTEND_SRC = BACKEND_ROOT.parent / "frontend" / "src"        # .../frontend/src

# Lista CONGELADA (Plan 85). Cambiarla es una decisión consciente con code review.
RESERVED_KEYS = frozenset({
    "STACKY_RUN_ADVISOR_ENFORCE",
    "STACKY_BUDGET_PER_TICKET_USD",
    "STACKY_BRIEF_MODEL_SELECT_ENABLED",
    "STACKY_SPECULATIVE_MODE",
})

def _production_corpus() -> str:
    """Concatena el código productivo donde un consumo cuenta como real.

    Incluye: backend/**/*.py y frontend/src/**/*.{ts,tsx}.
    Excluye: backend/tests/** (los tests no son consumo) y
             backend/services/harness_flags.py (el registry se define ahí).
    NOTA: harness_profiles.py y config.py SÍ cuentan (baseline de la
    auditoría 2026-07-02; endurecerlo es fuera de scope, sección 6).
    """
    parts: list[str] = []
    for path in sorted(BACKEND_ROOT.rglob("*.py")):
        rel = path.relative_to(BACKEND_ROOT).as_posix()
        if rel.startswith("tests/") or rel == "services/harness_flags.py":
            continue
        parts.append(path.read_text(encoding="utf-8", errors="ignore"))
    if FRONTEND_SRC.exists():
        for pattern in ("*.ts", "*.tsx"):
            for path in sorted(FRONTEND_SRC.rglob(pattern)):
                if "__tests__" in path.parts:
                    continue
                parts.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(parts)

@pytest.fixture(scope="module")
def corpus() -> str:
    return _production_corpus()

def test_every_non_reserved_flag_is_wired(corpus):
    dead = [
        spec.key for spec in FLAG_REGISTRY
        if not spec.reserved and spec.key not in corpus
    ]
    assert dead == [], (
        f"Flags registradas SIN consumidor en código productivo: {dead}. "
        "O se cablean, o se marcan reserved=True con reserved_reason "
        "y se agregan a RESERVED_KEYS de este test."
    )

def test_reserved_set_is_frozen():
    actual = {spec.key for spec in FLAG_REGISTRY if spec.reserved}
    assert actual == RESERVED_KEYS

def test_reserved_flags_declare_reason():
    for spec in FLAG_REGISTRY:
        if spec.reserved:
            assert spec.reserved_reason.strip(), f"{spec.key} sin reserved_reason"

def test_reserved_flags_are_actually_dead(corpus):
    """Anti-deriva inversa: si alguien cablea una reservada, DEBE quitarle la marca."""
    alive = [k for k in RESERVED_KEYS if k in corpus]
    assert alive == [], (
        f"Flags marcadas reserved pero CON consumidor real: {alive}. "
        "Quitarles reserved=True (ya están vivas)."
    )
```

**Caso borde cubierto:** substring accidental (una key que sea prefijo de otra, p.ej. `STACKY_RUN_ADVISOR_ENFORCE` vs `STACKY_RUN_ADVISOR_ENABLED`): el match por substring solo puede dar **falsos vivos**, nunca falsos muertos — dirección segura para el centinela (no rompe CI de más). `STACKY_RUN_ADVISOR_ENFORCE` no es substring de ninguna otra key (verificado: `_ENABLED` ≠ `_ENFORCE`).

**Comando (desde `Stacky Agents/backend`, con el venv del repo):**
```
.venv\Scripts\python.exe -m pytest tests/test_flag_wiring.py -q
```

**Criterio de aceptación binario F0:** el test recién escrito FALLA con `AttributeError` (FlagSpec aún no tiene `reserved`) o, tras F1 parcial sin marcar las 4, falla listando exactamente esas 4 keys en `test_every_non_reserved_flag_is_wired`. Fallar por otra razón = investigar antes de seguir.

**Flag protectora:** no aplica (test puro, sin efecto runtime). **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F1 — Campos `reserved`/`reserved_reason` en `FlagSpec` + marcar las 4

**Objetivo:** declarar en el registry, con razón textual, qué flags son reservadas.

**Archivo a editar:** `Stacky Agents/backend/services/harness_flags.py`

**Cambio 1 — dataclass (línea ~19-27), agregar al FINAL de los campos:**
```python
    reserved: bool = False        # Plan 85 — True = declarada para fase diferida, SIN consumidor aún
    reserved_reason: str = ""     # Plan 85 — obligatoria si reserved=True (qué fase la cablea)
```
(NO tocar `default` ni ningún campo existente; `FlagSpec` es frozen, los campos nuevos van con default → cero impacto en las 135 specs restantes.)

**Cambio 2 — las 4 specs, agregar exactamente:**

- En `key="STACKY_RUN_ADVISOR_ENFORCE"` (línea ~587):
  ```python
        reserved=True,
        reserved_reason="Plan 22 V2.2 (smart dispatch enforce) declarada anticipadamente; el enforcement nunca se implementó.",
  ```
- En `key="STACKY_BUDGET_PER_TICKET_USD"` (línea ~598):
  ```python
        reserved=True,
        reserved_reason="Plan 22 V2.2 (budget por ticket) declarada anticipadamente; el tope de costo nunca se implementó. Hoy NO limita nada.",
  ```
- En `key="STACKY_BRIEF_MODEL_SELECT_ENABLED"` (línea ~1276):
  ```python
        reserved=True,
        reserved_reason="Superseded por Plan 43: el selector model/effort de run-brief quedó siempre activo, sin gate. Esta flag nunca se cableó.",
  ```
- En `key="STACKY_SPECULATIVE_MODE"` (línea ~1654):
  ```python
        reserved=True,
        reserved_reason="Plan 57 v1 solo opera modo eager; la lectura del modo quedó diferida a v1.1 (F2a post-GA).",
  ```

**Decisión explícita: NO se borra ninguna flag.** Las 4 corresponden a fases diferidas documentadas o supersesión; borrarlas rompería `.env` existentes, perfiles y la trazabilidad de los planes 22/42/57. Marcar `reserved` es reversible en 1 línea cuando la fase se implemente (y `test_reserved_flags_are_actually_dead` obligará a hacerlo).

**Criterio de aceptación binario F1:**
```
.venv\Scripts\python.exe -m pytest tests/test_flag_wiring.py tests/test_harness_flags.py -q
```
→ los 4 tests de F0 en verde Y `test_harness_flags.py` completo sigue verde (en particular `test_every_registry_flag_is_categorized` y `test_default_known_only_for_curated`).

**Flag protectora:** no aplica (metadata declarativa). **Impacto por runtime:** ninguno (ningún runner lee estos campos). **Trabajo del operador:** ninguno.

---

### F2 — Exponer `reserved`/`reserved_reason` en la API

**Objetivo:** que `GET /api/harness-flags` incluya los campos nuevos por flag.

**Archivo a editar:** `Stacky Agents/backend/services/harness_flags.py`, función `read_current()` (línea ~1928). En el dict de `result.append({...})` (línea ~1948), agregar:
```python
            "reserved": spec.reserved,
            "reserved_reason": spec.reserved_reason,
```

**Test PRIMERO — agregar a `Stacky Agents/backend/tests/test_flag_wiring.py`:**
```python
def test_read_current_exposes_reserved_fields():
    from services.harness_flags import read_current
    flags = {f["key"]: f for f in read_current()}
    assert flags["STACKY_BUDGET_PER_TICKET_USD"]["reserved"] is True
    assert flags["STACKY_BUDGET_PER_TICKET_USD"]["reserved_reason"]
    assert flags["STACKY_RUN_ADVISOR_ENABLED"]["reserved"] is False
```
(Si `read_current()` requiere `config`, seguir el patrón de mocking ya usado en `tests/test_harness_flags.py` para las funciones que importan `from config import config` — import lazy dentro de la función: parchear en el módulo origen.)

**Nota PUT:** `put_harness_flags` (`backend/api/harness_flags.py:117`) NO se toca — las reservadas siguen siendo editables/persistibles (el operador puede dejar el valor preseteado para cuando la fase llegue; human-in-the-loop).

**Criterio binario F2:** el test nuevo verde con el mismo comando de F1.

**Flag protectora:** no aplica (campo aditivo en respuesta JSON; los clientes existentes ignoran claves desconocidas). **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F3 — Badge "Reservada — sin efecto" en la UI

**Objetivo:** que el operador VEA en el panel qué perillas no tienen efecto todavía, y por qué (tooltip).

**Archivos a editar:**

1. `Stacky Agents/frontend/src/api/endpoints.ts` — en `interface HarnessFlagView` (línea 652), agregar tras `env_only: boolean;`:
   ```typescript
     reserved?: boolean;         // Plan 85 — declarada para fase diferida, sin consumidor
     reserved_reason?: string;   // Plan 85 — por qué / qué fase la cablea
   ```
   (Opcionales `?` para tolerar backends viejos — backward compatible.)

2. `Stacky Agents/frontend/src/components/HarnessFlagsPanel.tsx` — en `FlagRow` (línea ~61), junto al badge existente `def:` (línea ~166), renderizar ANTES de él:
   ```tsx
   {flag.reserved && (
     <span
       className={styles.reservedBadge}
       title={flag.reserved_reason || "Declarada para una fase futura; hoy ningún código la lee."}
     >
       reservada — sin efecto
     </span>
   )}
   ```

3. `Stacky Agents/frontend/src/components/HarnessFlagsPanel.module.css` — agregar clase:
   ```css
   .reservedBadge {
     font-size: 0.7rem;
     padding: 0 6px;
     border-radius: 8px;
     background: color-mix(in srgb, var(--color-warning, #b8860b) 18%, transparent);
     color: var(--color-warning, #b8860b);
     border: 1px solid color-mix(in srgb, var(--color-warning, #b8860b) 40%, transparent);
     white-space: nowrap;
   }
   ```
   (Si `--color-warning` no existe en el tema, el fallback `#b8860b` aplica solo; no agregar variables globales nuevas.)

4. `Stacky Agents/frontend/src/components/__tests__/HarnessFlagsPanel.test.tsx` — SI vitest está operativo en el entorno, agregar un caso: un flag con `reserved: true` renderiza el texto `reservada — sin efecto`. SI vitest no corre en este entorno (limitación conocida del repo), el criterio de F3 es solo el typecheck.

**Criterio binario F3 (desde `Stacky Agents/frontend`):**
```
npx tsc --noEmit
```
→ exit code 0.

**No se deshabilita el control** (el operador puede presetear valores); el badge + tooltip son la señal honesta.

**Flag protectora:** no aplica — el badge solo aparece si `reserved: true` viene en los datos (data-driven; sin datos nuevos no cambia ni un pixel). **Impacto por runtime:** ninguno (solo panel). **Trabajo del operador:** ninguno.

---

### F4 — Ratchet: registrar el test nuevo

**Objetivo:** que `test_flag_wiring.py` corra en el gate de tests del arnés (regla del Plan 49 F4: todo test nuevo del backend va en `HARNESS_TEST_FILES` o el meta-test falla).

**Archivos a editar:**
- `Stacky Agents/backend/scripts/run_harness_tests.sh` — agregar `tests/test_flag_wiring.py` a `HARNESS_TEST_FILES`, en orden alfabético relativo a los vecinos.
- `Stacky Agents/backend/scripts/run_harness_tests.ps1` — ídem en la lista equivalente.

**Criterio binario F4:** el meta-test del ratchet (Plan 49 F4, en la suite de `tests/`) en verde, y:
```
.venv\Scripts\python.exe -m pytest tests/test_flag_wiring.py tests/test_harness_flags.py -q
```
→ todo verde.

**Flag protectora:** no aplica. **Impacto por runtime:** ninguno. **Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El corpus del centinela lee ~900 archivos por corrida de test | Fixture `scope="module"`, una sola lectura; medido en repos similares < 1 s. Si excediera 5 s, cachear por mtime — pero NO optimizar preventivamente. |
| Falso "vivo" por match en comentarios o en `config.py`/`harness_profiles.py` (set sin read) | Aceptado y documentado: el centinela solo puede pecar de permisivo, nunca rompe CI de más. La auditoría 2026-07-02 con este mismo baseline encontró exactamente 4 muertas. Endurecer el criterio = fuera de scope. |
| Colisión con planes 82/83/84 (agregan campos a `FlagSpec`) | Campos aditivos con default al final del dataclass; orden de implementación independiente. Quien implemente segundo solo aprieta `Edit` en líneas distintas. |
| Una fase futura cablea una reservada y olvida desmarcarla | `test_reserved_flags_are_actually_dead` falla y obliga a quitar `reserved=True` + sacar la key de `RESERVED_KEYS`. |
| Tocar `default` por error en las 4 specs | Prohibido explícito (guardarraíl 6); F1 solo AGREGA `reserved`/`reserved_reason`. |
| Suite completa del backend contaminada (~40F/449E conocidos) | Validar por archivo (`test_flag_wiring.py` + `test_harness_flags.py`), patrón estándar del repo. |

## 6. Fuera de scope

- **Borrar** cualquiera de las 4 flags (romper `.env`/perfiles/trazabilidad; reversibilidad > limpieza).
- Endurecer el criterio de "consumo" (distinguir set vs read, excluir `config.py`/`harness_profiles.py`, parsear AST): el baseline por literal es suficiente y solo-permisivo.
- Implementar V2.2 (enforce/budget) o Plan 57 v1.1 (modo lazy): eso des-reserva las flags cuando ocurra.
- Deshabilitar la edición de flags reservadas en la UI.
- Tocar `put_harness_flags`, perfiles, o cualquier camino de ejecución de los 3 runtimes.

## 7. Glosario

- **FLAG_REGISTRY / FlagSpec:** catálogo declarativo de ~139 flags del arnés (`backend/services/harness_flags.py`); fuente única que la UI renderiza dinámicamente (Plan 33/62/63).
- **Flag placebo:** key registrada (visible/editable en el panel) que ningún código productivo lee → togglearla no tiene efecto.
- **Reservada:** flag declarada a propósito para una fase diferida que aún no se implementó; se marca `reserved=True` con razón.
- **Centinela:** test que congela una invariante estructural y rompe CI a propósito si se viola (patrón Planes 49/61/63).
- **Ratchet / HARNESS_TEST_FILES:** listas en `backend/scripts/run_harness_tests.{sh,ps1}` donde debe registrarse todo test nuevo del backend (meta-test del Plan 49 F4).
- **HarnessFlagsPanel:** panel React (`frontend/src/components/HarnessFlagsPanel.tsx`) que renderiza el registry por categorías (Plan 62/63/78).

## 8. Orden de implementación

1. F0 — escribir `tests/test_flag_wiring.py`; verificar que falla por la razón correcta.
2. F1 — campos en `FlagSpec` + marcar las 4 specs; F0 en verde.
3. F2 — test del serializador; exponer campos en `read_current()`; verde.
4. F3 — tipo TS + badge + CSS; `npx tsc --noEmit` exit 0.
5. F4 — registrar en ratchet sh+ps1; meta-test verde.

## 9. Definición de Hecho (DoD)

- [ ] `tests/test_flag_wiring.py` existe con los 5 tests nombrados y pasa con el venv del repo.
- [ ] `FlagSpec` tiene `reserved`/`reserved_reason` con defaults; solo las 4 keys de la tabla los declaran.
- [ ] `GET /api/harness-flags` expone `reserved`/`reserved_reason` por flag.
- [ ] El panel muestra el badge "reservada — sin efecto" con tooltip en exactamente 4 flags; `npx tsc --noEmit` limpio.
- [ ] `test_harness_flags.py` completo sigue verde (categorización y curated defaults intactos).
- [ ] Test nuevo registrado en `run_harness_tests.sh` y `.ps1`.
- [ ] Ningún archivo de runners/runtime tocado (diff limitado a: `services/harness_flags.py`, `tests/test_flag_wiring.py`, `frontend/src/api/endpoints.ts`, `HarnessFlagsPanel.tsx`, `HarnessFlagsPanel.module.css`, opcional su test, y los 2 scripts de ratchet).
- [ ] Trabajo del operador: ninguno.
