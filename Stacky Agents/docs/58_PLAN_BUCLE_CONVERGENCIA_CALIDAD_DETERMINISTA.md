# Plan 58 — Bucle de Convergencia de Calidad Determinista

> Estado: PROPUESTO (2026-06-20). Autor: StackyArchitectaUltraEficientCode.
> Finalista #1 del roadmap `docs/_roadmap/TOP5_2026-06-20_POST57_LOOP_MOLECULA_BIDIRECCIONAL.md`.
> Pensado para que un modelo MENOR (Haiku/Codex/Copilot) lo implemente sin inferir nada.

---

## 1. Título, objetivo y KPI

**Título:** Bucle de convergencia de calidad determinista para el pase correctivo de la épica.

**Objetivo (1 frase):** Convertir el pase correctivo de épica de *single-shot* (un único intento que pide re-emisión y se detiene) en un **bucle determinista ACOTADO** que re-evalúa el output con el gate ya implementado (`evaluate_epic_gate`), dispara un pase correctivo dirigido al defecto, **RE-EVALÚA** y repite hasta `PASS` o agotar un presupuesto (>1) de iteraciones.

**Qué NO es:** no es subir un cap (eso sería tuning). Hoy NO existe ningún lazo que re-evalúe el output contra el veredicto del gate después de pedir la corrección — se pide UNA vez y se publica lo que haya. Este plan introduce ese lazo.

**KPI medible con telemetría existente (sin instrumentación nueva de negocio):**
- **Primario:** baja la proporción de runs `business`/épica que terminan en `needs_review` por defecto estructural reparable (`structural_defects` ⊂ reparables), **sin trabajo del operador**. Medible vía `metadata["epic_summary"]` (campo nuevo `convergence`, ver F4) y el panel `harness_health` (runs por status).
- **Secundario:** con el flag OFF, comportamiento **byte-idéntico** al actual (un solo pase). Verificable por test (F5) y por diff del payload de `epic_summary` sin el flag.
- **Costo:** acotado por `cap_iteraciones` (default 2). Telemetría `convergence.iterations` permite ver el costo real por run.

---

## 2. Por qué ahora / gap (con evidencia firsthand 2026-06-20)

El pase correctivo de épica vive en `backend/services/claude_code_cli_runner.py:911-976`. Su forma actual:

1. `if not _epic_repair_done[0] and event.type == "result" and STACKY_EPIC_REPAIR_ENABLED and one_shot and business:` (líneas 911-917).
2. Marca `_epic_repair_done[0] = True` (línea 918) — **se arma de no repetir nunca**.
3. Extrae HTML (`_extract_epic_html`), corre `evaluate_epic_gate(...)` (líneas 935-942) y, si `decision == REPAIR`, **envía UN** mensaje correctivo por `_send_system_message` (línea 962).
4. **NO re-extrae el output re-emitido, NO vuelve a correr el gate, NO repite.** El run continúa y se publica lo que el agente haya dejado, sin verificar que la corrección efectivamente convergió.

Es decir: el gate (plan 51) ya da un veredicto determinista PASS/REPAIR/NEEDS_REVIEW, y el patrón de pase correctivo (plan 32, `acceptance_gate.attempt_acceptance_repair`) ya sabe enviar un mensaje + re-chequear UNA vez. **Lo que falta es cerrar el lazo:** evaluar → corregir → **re-evaluar** → repetir hasta PASS o presupuesto.

**Ortogonalidad (dejarlo explícito para el implementador):** los loops `while retries < max_retries` de `backend/services/cli_autocorrect.py:153` y `backend/services/codex_autocorrect.py:85` SÍ son bucles, pero reaccionan a **errores de ejecución** (`report.ok` del runner), NO a la **calidad del entregable** (veredicto del gate). Este plan es ORTOGONAL a esos: no los toca ni los reusa.

**Por qué importa:** cada `needs_review` evitable consume atención del operador. El agente muchas veces corrige a la primera, pero cuando no, hoy se publica un candidato defectuoso o se degrada a `needs_review` aunque un segundo pase dirigido lo habría resuelto. Cerrar el lazo, acotado y opt-in, recupera esos casos sin agregar trabajo humano.

---

## 3. Principios y guardarraíles (codificados en el diseño)

1. **Reusar, no crear:** el bucle reusa `harness.epic_gate.evaluate_epic_gate` (re-evaluación) y el PATRÓN de `services/acceptance_gate.attempt_acceptance_repair` (send_fn + `supports_resume` + budget). **Cero servicios nuevos de generación.** La pieza nueva es una función PURA de orquestación (`run_convergence_loop`) y el wiring que la llama.
2. **Default seguro OFF:** flag `STACKY_QUALITY_CONVERGENCE_ENABLED` default `False`. Con OFF, el código toma exactamente el camino actual (un solo pase). Byte-idéntico.
3. **Presupuesto acota costo:** flag `STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS` default `2` (≥1; un valor 1 ⇒ equivale al single-shot actual). El bucle nunca excede ese tope de **pases correctivos**.
4. **Config por UI (regla dura, innegociable):** AMBOS flags se registran en `backend/services/harness_flags.py` (`FLAG_REGISTRY`) → quedan **editables por UI** (plan 33 ya consume el registry) y documentados en `backend/.env.example`. NO son env-only.
5. **Paridad 3 runtimes con fallback graceful:** el lazo necesita `send_fn` + `supports_resume`. Runtime SIN `supports_resume` ⇒ **degrada a pase único** (comportamiento actual), de forma explícita y sin error. Ver tabla §3.1.
6. **Human-in-the-loop intacto:** el bucle produce un **CANDIDATO**. El operador sigue aprobando/rechazando exactamente igual. NO auto-publica nada nuevo, NO cambia quién decide. El autopublish de épica (pedido explícito histórico) sigue tal cual; el lazo corre ANTES, mejorando el candidato que igual se publica/revisa.
7. **No degradar:** flag OFF = idéntico. El cap acota tokens. La función de orquestación es PURA y determinista (sin LLM, sin reloj, sin red) salvo las `send_fn`/`reextract_fn` inyectadas.
8. **Mono-operador sin auth:** no se introduce ningún concepto de usuario/rol.

### 3.1 Soporte de resume por runtime (firsthand: `backend/harness/capabilities.py:21-43`)

| Runtime | `supports_resume` | Comportamiento del bucle |
|---|---|---|
| `claude_code_cli` | `True` (capabilities.py:26) | **Bucle completo.** El wiring vive en `claude_code_cli_runner.py` (único runner que autopublica épica — ver `backend/services/claude_code_cli_runner.py:1212`). |
| `codex_cli` | `True` (capabilities.py:34, vía `codex exec resume <session_id>`) | Capaz en teoría, pero **NO autopublica épica** (sólo Claude CLI lo hace). El bucle de épica **no aplica** a Codex. La función PURA queda lista para reuso futuro; no hay wiring de épica para Codex en este plan (fuera de scope, §6). |
| `github_copilot` | `False` (capabilities.py:42) | **Degrada a pase único.** `run_convergence_loop` detecta `supports_resume=False` y devuelve `degraded_no_resume` sin iterar. No autopublica épica de todos modos. |

> Nota para el implementador: el wiring real de este plan es **Claude-CLI-only** porque es el único runtime que ejecuta el pase correctivo de épica + autopublish. La función `run_convergence_loop` se diseña **agnóstica de runtime** (recibe `runtime`, `send_fn`, `reextract_fn`) para que (a) sea testeable sin Claude y (b) un plan futuro la reuse en Codex sin reescribir. NO inventar wiring para Codex/Copilot acá.

---

## 4. Fases

> Orden estricto por dependencia. Cada fase es autocontenida, test-first. Intérprete del repo: `.venv\Scripts\python.exe`. Ejecutar tests desde `Stacky Agents/backend`.

---

### F0 — Flags de convergencia (config + registry + .env.example)

**Objetivo:** declarar los dos flags nuevos (enable + cap) como atributos de `Config` y en el `FLAG_REGISTRY` para que la UI los edite. **Valor:** habilita activación/edición por UI sin tocar frontend (plan 33).

**Archivos exactos a tocar:**
- `backend/config.py`
- `backend/services/harness_flags.py`
- `backend/.env.example`

**F0.1 — `backend/config.py`**
Agregar dos atributos a la clase `Config` (mismo patrón que `STACKY_ACCEPTANCE_REPAIR_MAX_RETRIES` en `config.py:403-404`):

```python
# Plan 58 — Bucle de convergencia de calidad determinista (épica).
# OFF por defecto: con OFF el pase correctivo de épica es single-shot (idéntico al actual).
STACKY_QUALITY_CONVERGENCE_ENABLED: bool = _env_bool(
    "STACKY_QUALITY_CONVERGENCE_ENABLED", False
)
# Máximo de PASES CORRECTIVOS del bucle (>=1). 1 == single-shot actual. Default 2.
STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS: int = _env_int(
    "STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS", 2
)
```

> Usá los helpers de lectura de env que ya existan en `config.py` (`_env_bool`/`_env_int` o el patrón equivalente que use el archivo — confirmá el nombre real leyendo cómo está definido `STACKY_ACCEPTANCE_REPAIR_MAX_RETRIES`). Caso borde: si el valor de env es `< 1`, **clamp a 1** en el punto de uso (F2), NO acá (config refleja lo seteado).

**F0.2 — `backend/services/harness_flags.py`**
Agregar al `FLAG_REGISTRY` (tupla) dos `FlagSpec` nuevos, group `"global"` (no es claude-specific en su semántica, aunque hoy solo lo use Claude):

```python
FlagSpec(
    key="STACKY_QUALITY_CONVERGENCE_ENABLED",
    type="bool",
    label="Bucle de convergencia de calidad (épica)",
    description="Plan 58 — Si ON, el pase correctivo de épica re-evalúa el gate y reintenta hasta PASS o agotar el presupuesto. OFF = un solo pase (actual).",
    group="global",
),
FlagSpec(
    key="STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS",
    type="int",
    label="Máx. iteraciones de convergencia",
    description="Plan 58 — Máximo de pases correctivos del bucle (>=1). 1 = single-shot. Default 2.",
    group="global",
),
```

**F0.3 — `backend/.env.example`**
Agregar (en la sección de flags globales/arnés, junto a otros `STACKY_*`):

```
# Plan 58 — Bucle de convergencia de calidad determinista (épica). Default OFF.
STACKY_QUALITY_CONVERGENCE_ENABLED=false
# Máximo de pases correctivos del bucle (>=1). 1 = single-shot. Default 2.
STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS=2
```

**TESTS PRIMERO** — archivo: `backend/tests/test_harness_flags.py` (ya existe; agregar casos).
Casos:
1. `test_convergence_flags_registered` — los dos keys aparecen en `{f.key for f in FLAG_REGISTRY}`.
2. `test_convergence_enabled_default_off` — `Config().STACKY_QUALITY_CONVERGENCE_ENABLED is False` (con env limpio).
3. `test_convergence_cap_default_two` — `Config().STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS == 2`.

**Comando exacto:**
```
.venv\Scripts\python.exe -m pytest "tests/test_harness_flags.py" -q
```

**Criterio de aceptación (binario):** el comando pasa en verde; los 3 casos nuevos incluidos.
**Flag que protege:** N/A (declaración). **Impacto runtime:** ninguno (solo declara). **Fallback:** N/A.
**Trabajo del operador:** ninguno (opt-in, default off).

---

### F1 — Función PURA de orquestación `run_convergence_loop`

**Objetivo:** una función PURA y agnóstica de runtime que ejecuta el lazo evaluar→corregir→re-evaluar con presupuesto y fallback. **Valor:** corazón del plan, testeable sin Claude ni red, reusable.

**Archivo nuevo exacto:** `backend/harness/convergence.py`

**Contrato EXACTO (firmas, nombres, tipos):**

```python
"""Plan 58 — Bucle de convergencia de calidad determinista.

PURO: sin LLM, sin red, sin reloj, sin disco, sin datos personales. Toda la
interacción con el mundo entra por callables inyectados (send_fn, reextract_fn,
evaluate_fn). Determinismo total dado el mismo input.

Reusa el VEREDICTO de harness.epic_gate.evaluate_epic_gate (via evaluate_fn) y
el PATRÓN de services.acceptance_gate.attempt_acceptance_repair (send_fn +
supports_resume + budget). NO genera contenido por sí mismo.
"""
from __future__ import annotations

from typing import Callable, NamedTuple

from harness.capabilities import CAPABILITIES
from harness.epic_gate import GateDecision, GateVerdict


class ConvergenceResult(NamedTuple):
    converged: bool            # True si el último veredicto fue PASS
    iterations: int            # nº de PASES CORRECTIVOS efectivamente enviados
    final_decision: str        # GateDecision.value del último veredicto ("pass"|"repair"|"needs_review")
    stop_reason: str           # ver constantes STOP_* abajo
    defects_first: list        # structural_defects del PRIMER veredicto (sorted)
    defects_last: list         # structural_defects del ÚLTIMO veredicto (sorted)


# stop_reason canónicos (strings estables para telemetría/tests):
STOP_CONVERGED = "converged"                 # alcanzó PASS
STOP_BUDGET_EXHAUSTED = "budget_exhausted"   # agotó max_iterations sin PASS
STOP_NO_RESUME = "degraded_no_resume"        # runtime sin supports_resume → pase único
STOP_NEEDS_REVIEW = "needs_review_terminal"  # veredicto NEEDS_REVIEW (no reparable inline)
STOP_NO_PROGRESS = "no_progress"             # el pase no cambió los defectos → abortar (anti-loop)
STOP_DISABLED = "disabled"                   # flag OFF (no debería llamarse, defensa)
STOP_SEND_FAILED = "send_failed"             # send_fn lanzó/retornó falsy


def run_convergence_loop(
    *,
    enabled: bool,
    runtime: str,
    max_iterations: int,
    initial_verdict: GateVerdict,
    build_repair_message: Callable[[GateVerdict], str],
    send_fn: Callable[[str], object] | None,
    reextract_and_evaluate_fn: Callable[[], GateVerdict],
) -> ConvergenceResult:
    """Ejecuta el lazo determinista de convergencia de calidad.

    Parámetros:
      enabled: flag STACKY_QUALITY_CONVERGENCE_ENABLED resuelto por el caller.
      runtime: nombre del runtime (clave de CAPABILITIES).
      max_iterations: presupuesto de PASES CORRECTIVOS (se clampa a >=1).
      initial_verdict: GateVerdict ya calculado sobre el output actual.
      build_repair_message: dado un GateVerdict, arma el mensaje correctivo dirigido.
      send_fn: envía el mensaje correctivo al runtime (None => no se puede reparar).
      reextract_and_evaluate_fn: re-extrae el output re-emitido y devuelve un nuevo
          GateVerdict. El caller encapsula acá la lectura de final_output +
          _extract_epic_html + evaluate_epic_gate.

    Reglas deterministas (en orden):
      0. cap = max(1, max_iterations).
      1. Si not enabled -> ConvergenceResult(converged=(decision==PASS), iterations=0,
         stop_reason=STOP_DISABLED, ...). (Defensa; el caller no debería llamar con OFF.)
      2. Si initial_verdict.decision == PASS -> converged=True, iterations=0, STOP_CONVERGED.
      3. Si initial_verdict.decision == NEEDS_REVIEW -> converged=False, iterations=0,
         STOP_NEEDS_REVIEW (no reparable inline; el caller degrada).
      4. cap_rt = CAPABILITIES.get(runtime); si cap_rt is None or not cap_rt.supports_resume
         or send_fn is None -> converged=False, iterations=0, STOP_NO_RESUME (pase único: NO
         envía nada; el caller, si quiere, ya hizo/ hará el single-shot histórico — ver F2 nota).
         [Para Copilot/runtime incapaz: NO se itera.]
      5. Bucle while sent < cap and current.decision == REPAIR:
           a. msg = build_repair_message(current)
           b. try: ok = send_fn(msg)  except -> STOP_SEND_FAILED (break, no incrementar más)
              if not ok -> STOP_SEND_FAILED (break)
           c. sent += 1
           d. nxt = reextract_and_evaluate_fn()
           e. if nxt.decision == PASS -> current=nxt; STOP_CONVERGED; break
              if nxt.decision == NEEDS_REVIEW -> current=nxt; STOP_NEEDS_REVIEW; break
              if sorted(nxt.structural_defects) == sorted(current.structural_defects)
                 -> current=nxt; STOP_NO_PROGRESS; break   # anti-loop: no avanzó
              current = nxt   # siguió en REPAIR pero con defectos distintos -> reintentar
         Al salir del while por budget: STOP_BUDGET_EXHAUSTED.
      6. Devolver ConvergenceResult con converged=(current.decision==PASS),
         iterations=sent, final_decision=current.decision.value,
         defects_first=sorted(initial_verdict.structural_defects),
         defects_last=sorted(current.structural_defects).

    NUNCA lanza: cualquier excepción de los callables se traduce a STOP_SEND_FAILED
    (en send_fn) o se propaga SOLO si viene de reextract_and_evaluate_fn antes del
    primer envío (defensivo: envolver y devolver STOP_SEND_FAILED). Mejor: envolver
    todo el cuerpo en try/except y, ante excepción inesperada, devolver converged=False,
    stop_reason=STOP_SEND_FAILED, iterations=sent_hasta_el_momento.
    """
```

> Implementación: traducir las reglas 0-6 a código. NO agregar lógica fuera de lo descrito. `GateDecision` se compara por identidad de enum (`current.decision == GateDecision.PASS`). `final_decision` se serializa con `.value`.

**Casos borde explícitos (cubrir en tests):**
- `max_iterations=0` ⇒ clamp a 1.
- `send_fn` retorna `None`/`False` ⇒ `STOP_SEND_FAILED`, `iterations` = pases ya enviados.
- Mismo set de defectos tras un pase ⇒ `STOP_NO_PROGRESS` (no quemar presupuesto en bucle estéril).
- Runtime `github_copilot` ⇒ `STOP_NO_RESUME`, `iterations=0`.

**TESTS PRIMERO** — archivo nuevo: `backend/tests/test_convergence_loop.py`.
Usar `GateVerdict` reales (es un `NamedTuple`, fácil de construir) y `reextract_and_evaluate_fn` como closure sobre una lista de veredictos pre-armados (cola). NO mockear Claude.

Casos (mínimo 10):
1. `test_already_pass_no_iterations` — initial PASS ⇒ converged=True, iterations=0, STOP_CONVERGED.
2. `test_needs_review_terminal` — initial NEEDS_REVIEW ⇒ converged=False, iterations=0, STOP_NEEDS_REVIEW.
3. `test_repair_then_pass_in_one` — initial REPAIR, primer reextract PASS ⇒ converged=True, iterations=1, STOP_CONVERGED.
4. `test_repair_twice_then_pass` — REPAIR→REPAIR(distintos defectos)→PASS con cap=2 ⇒ converged=True, iterations=2.
5. `test_budget_exhausted` — siempre REPAIR (defectos cambiantes), cap=2 ⇒ converged=False, iterations=2, STOP_BUDGET_EXHAUSTED.
6. `test_no_progress_aborts` — REPAIR con mismos defectos tras pase ⇒ STOP_NO_PROGRESS, iterations=1.
7. `test_copilot_degrades_single` — runtime="github_copilot" ⇒ STOP_NO_RESUME, iterations=0.
8. `test_send_fn_none` — send_fn=None ⇒ STOP_NO_RESUME (regla 4), iterations=0.
9. `test_send_fn_returns_falsy` — send_fn ⇒ False ⇒ STOP_SEND_FAILED, iterations=0.
10. `test_max_iterations_clamped_to_one` — max_iterations=0, REPAIR→PASS ⇒ converged=True, iterations=1.
11. `test_disabled_returns_disabled` — enabled=False ⇒ STOP_DISABLED, iterations=0.
12. `test_defects_first_and_last_recorded` — verifica `defects_first`/`defects_last` sorted.

**Comando exacto:**
```
.venv\Scripts\python.exe -m pytest "tests/test_convergence_loop.py" -q
```

**Criterio de aceptación (binario):** comando en verde, ≥11 casos. La función no lanza en ninguno.
**Flag que protege:** la propia función respeta `enabled`. **Impacto runtime:** ninguno (todavía no se cablea). **Fallback:** integrado (STOP_NO_RESUME).
**Trabajo del operador:** ninguno.

---

### F2 — Wiring del bucle en el runner Claude CLI (reemplaza el single-shot)

**Objetivo:** sustituir el bloque single-shot de pase correctivo de épica (`claude_code_cli_runner.py:911-976`) por una invocación a `run_convergence_loop` cuando el flag está ON, conservando el camino actual cuando está OFF. **Valor:** activa el lazo end-to-end en el único runtime que publica épica.

**Archivo exacto:** `backend/services/claude_code_cli_runner.py`

**Diseño del cambio (mínimo, con casos borde):**

El bloque actual (911-976) hace: detectar `event.type=="result"` + condiciones → `_epic_repair_done[0]=True` → extraer → gate → enviar UN mensaje. Lo que cambia:

1. **Cuando `STACKY_QUALITY_CONVERGENCE_ENABLED` está OFF (default):** comportamiento **idéntico** al actual. NO tocar la rama existente; envolverla en `if not config.STACKY_QUALITY_CONVERGENCE_ENABLED:` y dejarla tal cual.

2. **Cuando está ON:** dentro del mismo `if not _epic_repair_done[0] and event.type=="result" and one_shot and business` (mantener el guard `_epic_repair_done[0]=True` para que el bloque corra una sola vez por run), construir las piezas y llamar `run_convergence_loop`:

```python
# Plan 58 — bucle de convergencia (solo si el flag está ON).
if config.STACKY_QUALITY_CONVERGENCE_ENABLED and getattr(config, "STACKY_EPIC_REPAIR_ENABLED", False):
    from harness.convergence import run_convergence_loop
    from harness.epic_gate import evaluate_epic_gate, GateDecision

    def _current_clean() -> str:
        _txt = "\n".join(final_output) if final_output else ""
        return _extract_epic_html(_txt)

    def _evaluate() -> "GateVerdict":
        _clean = _current_clean()
        return evaluate_epic_gate(
            clean_html=_clean,
            structural_warnings=_epic_grounding_warnings(_clean),
            process_catalog=None,            # idéntico al wiring actual (línea 939): catálogo se evalúa en autopublish
            catalog_blocking_enabled=False,  # idem línea 940
            looks_like_epic_fn=_looks_like_epic,
        )

    def _build_msg(verdict) -> str:
        # Mensaje correctivo DIRIGIDO al defecto. Reusa el texto base actual
        # (líneas 953-961) y, si hay structural_defects, los enumera.
        base = (
            "Tu último mensaje no cumple el contrato de la épica. "
            "Re-emití AHORA, como único contenido del mensaje, EXCLUSIVAMENTE el HTML "
            "de la épica dentro de un único bloque ```html ... ```: <h1> con el título, "
            "el resumen ejecutivo y los bloques <hr><h2>RF-XXX consecutivos y SIN "
            "duplicados ni headings vacíos. SIN narración, SIN preámbulo, SIN archivos."
        )
        if verdict.structural_defects:
            base += "\nDefectos detectados: " + ", ".join(verdict.structural_defects) + "."
        return base

    _budget = max(1, int(config.STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS))
    _initial = _evaluate()
    _conv = run_convergence_loop(
        enabled=True,
        runtime=RUNTIME,
        max_iterations=_budget,
        initial_verdict=_initial,
        build_repair_message=_build_msg,
        send_fn=lambda m: _send_system_message(execution_id, m),
        reextract_and_evaluate_fn=_evaluate,
    )
    _epic_repair_result[0] = {
        "attempted": _conv.iterations > 0,
        "converged": _conv.converged,
        "iterations": _conv.iterations,
        "final_decision": _conv.final_decision,
        "stop_reason": _conv.stop_reason,
        "defects_first": _conv.defects_first,
        "defects_last": _conv.defects_last,
    }
    log("info", f"convergence: {_epic_repair_result[0]}")
else:
    # ... rama OFF: el bloque single-shot ACTUAL, sin cambios ...
```

**Casos borde a respetar:**
- `final_output` puede estar vacío en el primer `result`: `_extract_epic_html("")` ya tolera vacío (igual que hoy). `_evaluate()` devuelve un veredicto (probablemente `not_epic`→REPAIR).
- `_send_system_message` puede devolver falsy si stdin ya cerró: la función PURA lo traduce a `STOP_SEND_FAILED` y corta. No tumbar el run.
- El guard `_epic_repair_done[0]=True` se setea ANTES de invocar el bucle, igual que hoy, para que el bloque no se re-dispare en `result` posteriores.
- El bucle re-extrae de `final_output`, que el reader thread va llenando tras cada `_send_system_message`. **Importante:** `reextract_and_evaluate_fn` lee `final_output` en el momento de la llamada. El patrón de espera entre envío y re-lectura es el MISMO que ya usa el runner para el single-shot (el `result` event llega tras procesar el turno). Si en la práctica el re-emit no estuviera disponible sincrónicamente, el peor caso es defectos sin cambio ⇒ `STOP_NO_PROGRESS` (graceful, sin colgar). NO agregar `sleep` ni polling nuevo.

> Restricción para el implementador: NO modificar `_maybe_autopublish_epic` (líneas 1212-1277). El bucle corre ANTES; el autopublish publica el candidato resultante como hoy. Human-in-the-loop intacto.

**TESTS PRIMERO** — archivo nuevo: `backend/tests/test_convergence_wiring.py`.
> El runner es difícil de instanciar entero. Estrategia: testear la **forma del payload** `_epic_repair_result` y la decisión de rama por flag mediante una función auxiliar extraída, O un test de integración ligero con dobles. Mínimo viable sin sobre-ingeniería:
- Extraer la construcción de `_epic_repair_result` a una helper PURA `build_convergence_payload(conv: ConvergenceResult) -> dict` en `harness/convergence.py` (así es testeable sin runner). Tests:
1. `test_payload_shape_converged` — payload tiene keys exactas: attempted, converged, iterations, final_decision, stop_reason, defects_first, defects_last.
2. `test_payload_attempted_false_when_zero_iterations`.
3. `test_flag_off_uses_legacy_path` — con `STACKY_QUALITY_CONVERGENCE_ENABLED=False`, la rama OFF no invoca `run_convergence_loop` (verificar con monkeypatch que `run_convergence_loop` NO se llama; usar un import-level patch o un flag-checker puro `should_use_convergence_loop(config) -> bool`).

> Recomendado: extraer también `should_use_convergence_loop(*, convergence_enabled: bool, epic_repair_enabled: bool) -> bool` puro a `harness/convergence.py` y testearlo (decide la rama). Esto evita instanciar el runner.

**Comando exacto:**
```
.venv\Scripts\python.exe -m pytest "tests/test_convergence_wiring.py" -q
```

**Criterio de aceptación (binario):** comando en verde; el flag OFF nunca llama al bucle (test 3 lo prueba).
**Flag que protege:** `STACKY_QUALITY_CONVERGENCE_ENABLED`. **Impacto runtime:** solo Claude CLI; OFF=idéntico. **Fallback:** Copilot/Codex no entran a esta rama de épica (sólo Claude autopublica); además `run_convergence_loop` degrada por `supports_resume`.
**Trabajo del operador:** ninguno (opt-in default off).

---

### F3 — No-regresión del camino single-shot (flag OFF byte-idéntico)

**Objetivo:** demostrar con un test que, con el flag OFF, el bloque de pase correctivo de épica se comporta exactamente como antes del plan 58. **Valor:** garantía de no-degradación, condición innegociable.

**Archivo exacto:** `backend/tests/test_convergence_wiring.py` (agregar casos; o reusar un test existente del epic_repair si lo hubiera).

**Caso:**
- `test_legacy_single_shot_unchanged_when_flag_off` — con `STACKY_QUALITY_CONVERGENCE_ENABLED=False` y `STACKY_EPIC_REPAIR_ENABLED=True`, `should_use_convergence_loop(...)` ⇒ `False`. (La rama legacy es la actual; su comportamiento ya está cubierto por los tests de epic_repair existentes — NO duplicarlos.)

**Comando exacto:**
```
.venv\Scripts\python.exe -m pytest "tests/test_convergence_wiring.py" -q
```

**Criterio de aceptación (binario):** verde. `should_use_convergence_loop` retorna False con flag OFF y True solo con ambos ON.
**Flag:** el propio flag OFF. **Impacto runtime:** ninguno. **Fallback:** N/A.
**Trabajo del operador:** ninguno.

---

### F4 — Telemetría de convergencia en `epic_summary` (observabilidad del KPI)

**Objetivo:** sellar el resultado del bucle en `metadata["epic_summary"]` para medir el KPI sin instrumentación nueva. **Valor:** el operador/los paneles ven cuántos runs convergieron y en cuántas iteraciones.

**Archivos exactos:** el constructor de `epic_summary` vive en `backend/api/tickets.py` (función que arma el dict `epic_summary`; localizar por `epic_summary` en `tickets.py` — es donde plan 42/44 sellan `confidence`/grounding). Si `epic_summary` no es accesible desde el runner en el momento del bucle, sellar bajo `metadata["epic_convergence"]` en el runner (más simple y desacoplado).

**Decisión determinística para el implementador (NO inferir):** sellar bajo **`metadata["epic_convergence"]`** directamente en `claude_code_cli_runner.py`, justo después de poblar `_epic_repair_result[0]` en F2:

```python
metadata["epic_convergence"] = {
    "enabled": True,
    "converged": _conv.converged,
    "iterations": _conv.iterations,
    "final_decision": _conv.final_decision,
    "stop_reason": _conv.stop_reason,
}
```

> Razón de la decisión: `epic_summary` se construye dentro de `autopublish_epic_from_run` (api/tickets.py), que corre DESPUÉS y en otro módulo; pasarle el resultado del bucle requeriría ensanchar su firma. `metadata["epic_convergence"]` es el canal ya usado para telemetría de runner (`runaway`, `epic_recovery`, etc., ver líneas 1271-1276) y lo consume el panel de salud. Menor acoplamiento, mismo valor.

**TESTS PRIMERO:** cubierto indirectamente por F2 (el payload). Agregar a `test_convergence_wiring.py`:
- `test_convergence_metadata_block_shape` — `build_convergence_payload` + el sellado producen un dict con keys `enabled, converged, iterations, final_decision, stop_reason`. (Test sobre la helper, no sobre el runner entero.)

**Comando exacto:**
```
.venv\Scripts\python.exe -m pytest "tests/test_convergence_wiring.py" -q
```

**Criterio de aceptación (binario):** verde; el dict de telemetría tiene las 5 keys. Con flag OFF, `metadata["epic_convergence"]` NO se setea (queda ausente).
**Flag:** `STACKY_QUALITY_CONVERGENCE_ENABLED`. **Impacto runtime:** solo metadata adicional cuando ON. **Fallback:** ausencia de la key cuando OFF (compatibilidad hacia atrás).
**Trabajo del operador:** ninguno.

---

### F5 — Suite + registro en el ratchet del arnés

**Objetivo:** registrar los archivos de test nuevos en el ratchet (plan 49 F4) para que no se borren silenciosamente, y correr la suite focalizada. **Valor:** blindaje de calidad del propio plan.

**Archivos exactos:**
- `backend/scripts/run_harness_tests.sh`
- `backend/scripts/run_harness_tests.ps1`

**Cambio:** agregar a la lista `HARNESS_TEST_FILES` (en AMBOS scripts) las rutas:
- `tests/test_convergence_loop.py`
- `tests/test_convergence_wiring.py`

> Regla dura (memoria del proyecto): todo test nuevo del backend debe ir en `HARNESS_TEST_FILES` de ambos scripts, o el meta-test del plan 49 F4 falla.

**TESTS PRIMERO:** el meta-test del ratchet (plan 49) ya verifica la consistencia; no hace falta test nuevo. Solo asegurar que el meta-test pasa tras agregar las rutas.

**Comando exacto (suite focalizada del plan):**
```
.venv\Scripts\python.exe -m pytest "tests/test_convergence_loop.py" "tests/test_convergence_wiring.py" "tests/test_harness_flags.py" -q
```
Y el meta-test del ratchet (nombre real según plan 49; típicamente en `tests/test_harness_ratchet*.py` o `tests/conformance/`):
```
.venv\Scripts\python.exe -m pytest -k "ratchet" -q
```

**Criterio de aceptación (binario):** ambos comandos en verde; el meta-test del ratchet reconoce los dos archivos nuevos.
**Flag:** N/A. **Impacto runtime:** ninguno. **Fallback:** N/A.
**Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación (codificada) |
|---|---|---|
| R1 | El bucle quema tokens reintentando sin avanzar. | `STOP_NO_PROGRESS` (defectos iguales ⇒ abortar) + cap duro `max_iterations` (default 2) + clamp ≥1. |
| R2 | Re-extracción asíncrona: `final_output` aún no tiene el re-emit al re-evaluar. | Peor caso = defectos sin cambio ⇒ `STOP_NO_PROGRESS`, graceful. NO se agregan sleeps/polling. El patrón de espera es el mismo del single-shot actual. |
| R3 | Romper el comportamiento actual con flag OFF. | Rama OFF = bloque legacy intacto, envuelto en `if not config.STACKY_QUALITY_CONVERGENCE_ENABLED`. Test F3 lo prueba. Byte-idéntico. |
| R4 | Runtime sin resume entra al bucle. | `run_convergence_loop` chequea `CAPABILITIES[runtime].supports_resume` y `send_fn is None` ⇒ `STOP_NO_RESUME`, iterations=0. Además sólo Claude CLI ejecuta esta rama de épica. |
| R5 | El bucle auto-publica algo sin operador. | NO toca `_maybe_autopublish_epic`. Produce un CANDIDATO; el flujo de aprobación/rechazo es idéntico. Human-in-the-loop intacto. |
| R6 | `send_fn` lanza y tumba el run. | `run_convergence_loop` envuelve `send_fn` en try/except ⇒ `STOP_SEND_FAILED`, nunca propaga. El wiring ya envuelve el bloque en try/except (líneas 975-976 actuales). |
| R7 | Flag editable solo por env (rompe regla dura). | F0.2 registra ambos en `FLAG_REGISTRY` ⇒ editable por UI (plan 33). |
| R8 | Test nuevos se borran sin aviso. | F5 los registra en `HARNESS_TEST_FILES` (ambos scripts) ⇒ meta-test ratchet los exige. |

---

## 6. Fuera de scope (explícito)

- **Wiring para Codex CLI / Copilot.** Sólo Claude CLI autopublica épica (`claude_code_cli_runner.py:1212`). La función `run_convergence_loop` queda lista para reuso futuro, pero NO se cablea en otros runners en este plan.
- **Bucle de convergencia para el contrato de aceptación de CÓDIGO** (`acceptance_gate`/`criteria_repair`). Este plan reusa su PATRÓN pero aplica el lazo SOLO a la épica. Extenderlo al código es otro plan.
- **Subir el cap de `STACKY_ACCEPTANCE_REPAIR_MAX_RETRIES`** (config.py:403). No se toca; es tuning ortogonal.
- **Cambios de UI/frontend.** Los flags aparecen automáticamente vía `FLAG_REGISTRY` (plan 33). No se escribe TS.
- **Nuevos gates o detectores de calidad.** Se reusa `evaluate_epic_gate` (plan 51) tal cual.
- **Catálogo bloqueante en el bucle.** Igual que el wiring actual (`process_catalog=None`, `catalog_blocking_enabled=False`): el catálogo se evalúa en autopublish, no en el lazo de forma.
- **Cualquier `sleep`/polling/heurística temporal** para esperar el re-emit.

---

## 7. Glosario, Orden de implementación y DoD

### Glosario
- **Gate de épica:** `harness.epic_gate.evaluate_epic_gate` → `GateVerdict(decision: PASS|REPAIR|NEEDS_REVIEW, structural_defects, catalog_unknown, blocking, regression_defects)`. PURO (plan 51).
- **Pase correctivo:** mensaje enviado al runtime vía `send_fn` pidiendo re-emitir el output corregido. PATRÓN: `acceptance_gate.attempt_acceptance_repair`.
- **`supports_resume`:** capacidad de un runtime de continuar la sesión (`harness/capabilities.py`). Claude=True, Codex=True, Copilot=False.
- **Single-shot:** comportamiento actual — un único pase correctivo sin re-evaluación.
- **Convergencia:** alcanzar `decision == PASS` dentro del presupuesto.
- **Candidato:** la épica resultante del bucle, que el operador aún aprueba/rechaza (human-in-the-loop).

### Orden de implementación (estricto)
1. **F0** (flags: config + registry + .env.example) — sin dependencias.
2. **F1** (`harness/convergence.py` + tests) — depende de F0 sólo conceptualmente; la función es autónoma.
3. **F2** (wiring en `claude_code_cli_runner.py`) — depende de F0 y F1.
4. **F3** (no-regresión flag OFF) — depende de F2.
5. **F4** (telemetría `metadata["epic_convergence"]`) — depende de F2.
6. **F5** (ratchet + suite) — última, depende de todos los archivos de test creados.

### Definition of Done (global, binario)
- [ ] `STACKY_QUALITY_CONVERGENCE_ENABLED` y `STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS` existen en `Config`, en `FLAG_REGISTRY` (editables por UI) y en `.env.example`.
- [ ] `backend/harness/convergence.py` existe con `run_convergence_loop`, `ConvergenceResult`, las constantes `STOP_*`, `build_convergence_payload`, `should_use_convergence_loop`.
- [ ] `tests/test_convergence_loop.py` ≥11 casos en verde.
- [ ] `tests/test_convergence_wiring.py` en verde (incluye `test_flag_off_uses_legacy_path`).
- [ ] `tests/test_harness_flags.py` en verde con los 3 casos nuevos.
- [ ] El wiring del runner usa la rama de convergencia SOLO con flag ON; OFF = bloque legacy intacto.
- [ ] `metadata["epic_convergence"]` se sella cuando ON; ausente cuando OFF.
- [ ] Ambos archivos de test nuevos en `HARNESS_TEST_FILES` (.sh y .ps1); meta-test ratchet verde.
- [ ] Comando agregado de verificación global en verde:
      `.venv\Scripts\python.exe -m pytest "tests/test_convergence_loop.py" "tests/test_convergence_wiring.py" "tests/test_harness_flags.py" -q`
- [ ] **Trabajo del operador: ninguno / opt-in default off.**
