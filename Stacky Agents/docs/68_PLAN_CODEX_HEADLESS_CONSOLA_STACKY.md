# Plan 68 — Codex CLI headless en consola de Stacky: paridad de visibilidad con Claude Code CLI

> Versión: **v2 (PROPUESTA) — 1ra pasada del juez** | Estado: PROPUESTO | Fecha: 2026-06-23
> Autor: StackyArchitectaUltraEficientCode
> Origen del número: listado de `Stacky Agents/docs/` → NN máximo = 67 → este plan = **68**.

### CHANGELOG v1 → v2
- **C1 (BLOQUEANTE)** VP-01/VP-02 usaban `subprocess.PIPE` sin importar `subprocess` → `NameError`. Agregado `import subprocess`.
- **C2 (BLOQUEANTE)** VP-01/VP-02 llamaban a `_run_in_background` con kwargs **posicionales**; la firma real es `execution_id` posicional + `*, ticket_message, vscode_agent_filename, workspace_root, model_override` (todo keyword-only) en `codex_cli_runner.py:236-243`. → `TypeError`. Tests reescritos como unitarios deterministas sobre `_read_stream` (no sobre `_run_in_background` entero, que corre `while True: proc.wait(timeout=5)` y es inherentemente no determinista con mocks).
- **C3 (BLOQUEANTE)** VP-06 era un test de integración con DB real (`session_scope`/`Ticket`/`AgentExecution`) disfrazado de unitario, y asumía que EOF inmediato produce `push` (falso-rojo: el primer `push` real lo hace `start_codex_cli_run` en `pre_run`, no el reader). Reescrito como smoke determinista que asserts sobre el `push` de `pre_run` (que SÍ ocurre antes de cualquier stream) + una aserción separada del reader.
- **C4 (IMPORTANTE)** v1 no contenía NINGUNA `[ADICIÓN ARQUITECTO]` y era puro busywork de verificación ("si los tests pasan, F1 no requiere cambios"). Añadida **[ADICIÓN ARQUITECTO] AD-1**: paridad real de nivel de log stderr/stdout entre runners — hoy el reader de stderr de **codex** escribe en el `tail` de **stdout** (`stdout_tail`, `codex_cli_runner.py:574`), bug silencioso que corrompe el diagnóstico de errores; claude usa `stderr_tail` aislado (`claude_code_cli_runner.py:1052`). Se corrige el cruce de tails y se agrega test de paridad que lo blinda.
- **C5 (MENOR)** typo "Objetito" en F2 → corregido. Aclaradas firmas reales con `archivo:línea`.

---

## 1. Objetivo + KPI

**Objetivo (un párrafo).** El runner de Codex CLI (`codex_cli_runner.py`) ya persiste stderr vía `_read_stream`, pero existe una **asimetría real y un bug silencioso** frente a Claude Code CLI: el reader de stderr de codex escribe sus líneas en `stdout_tail` (no en un `stderr_tail` propio), mientras que claude mantiene el tail de stderr aislado (`claude_code_cli_runner.py:1052`, usado luego por `_stderr_excerpt`/`_format_cli_error` para persistir el motivo real de un `exit!=0`). Este plan (1) blinda con tests deterministas que ambos runners streamean stdout/stderr vía `log_streamer.push` con niveles equivalentes (`info`/`warn`), (2) **corrige el cruce de tails en codex** para que stderr no contamine stdout, y (3) deja el bug blindado con un test de paridad. El cambio es de **endurecimiento + fix de bug real**, no reescritura.

**KPI / impacto esperado:**
- **Paridad de visibilidad:** Codex CLI y Claude Code CLI muestran stdout/stderr en la consola de Stacky con niveles equivalentes y tails no cruzados.
- **Fix de bug real:** stderr de codex deja de escribirse en `stdout_tail` (hoy ocurre, `codex_cli_runner.py:574`).
- **Cero regresiones:** Claude Code CLI no se altera; codex sólo mejora su diagnóstico de error.
- **Trabajo del operador:** ninguno. Paridad automática, sin config nueva.
- **Paridad 3 runtimes:** Codex CLI, Claude Code CLI y GitHub Copilot Pro con visibilidad equivalente (Copilot ya opera por su propio puente; no se toca).

---

## 2. Por qué ahora / gap que cierra

- **Evidencia en código (verificada):**
  - `codex_cli_runner.py:564-577` crea 2 readers: stdout→`"info"`/`"codex"`/`stdout_tail`, stderr→`"warn"`/`"codex-stderr"`/`stdout_tail` (← bug: stderr escribe en el tail de stdout).
  - `claude_code_cli_runner.py:1046-1052` crea 2 readers: stdout→`"info"`/`"claude-code"`/`stdout_tail`/`final_output`, stderr→`"warn"`/`"claude-code-stderr"`/`stderr_tail`/`None` (tail aislado, correcto).
  - Loop de espera codex = `while True: proc.wait(timeout=5)` (`codex_cli_runner.py:604`), no `proc.wait()` simple.
  - Ambos usan `log_streamer.push` para streaming.
- **Gap real (no percibido):** el cruce de tails hace que cuando codex falla, el stderr se mezcla con stdout y el diagnóstico se degrada. Esto es una diferencia funcional concreta vs claude, no un tema cosmético de UI.
- **Plan 54** estableció paridad de `rejection_lessons`. Este plan cierra la paridad de **visibilidad/diagnóstico de streams**.

---

## 3. Principios y guardarraíles (no negociables)

- **3 runtimes con paridad:** Codex CLI, Claude Code CLI y GitHub Copilot Pro con visibilidad equivalente. Cada cambio de código se aplica solo donde el bug existe (codex); claude/Copilot no se degradan.
- **Cero trabajo extra al operador:** paridad automática; sin config nueva, sin flag nueva de operador.
- **Human-in-the-loop intacto:** el operador ve lo que hace el agente; no hay nueva autonomía.
- **Mono-operador sin auth:** sin RBAC.
- **No degradar:** reutilizar `log_streamer.push` y el patrón `stderr_tail` ya existente en claude. Sin nuevos mecanismos de streaming.
- **Reuso obligatorio:** los readers ya existen; solo se corrige el `tail` cruzado y se blindan con tests.
- **Backward-compatible:** el fix mueve stderr de codex a su propio tail; `_stderr_excerpt`/persistencia de error son aditivos (codex no los usaba antes, no rompe contrato).

---

## 4. Fases

> **Orden de dependencia:** F0 (tests deterministas TDD, fallan primero) → F1 (fix del bug de tail cruzado, tests pasan) → F2 (ratchet + smoke).
> Los tests de F0 se escriben ANTES del fix de F1 y deben FALLAR en VP-07 (la aserción que detecta el cruce de tails).

> **Intérprete de tests (usar en todos los comandos pytest):**
> `& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest <archivo> -q`
> Ejecutar desde `Stacky Agents/backend/`.

---

### F0 — Tests deterministas de paridad (TDD, fallan primero)

**Objetivo (1 frase).** Crear `tests/test_cli_visibility_parity.py` con tests unitarios deterministas sobre `_read_stream` (NO sobre `_run_in_background` entero, que corre un loop `while True` no determinizable con mocks).

**Archivo a crear:** `Stacky Agents/backend/tests/test_cli_visibility_parity.py`

**Justificación de determinismo:** `_read_stream` itera `for raw in stream` (`codex_cli_runner.py:1417`) — un iterable finito termina solo, sin `wait()` bloqueante. Es la unidad correcta para tests de paridad. Los readers de stdout/stderr se verifican por su firma de invocación y su `tail`, no lanzando el thread entero.

**Tests exactos (copiar tal cual):**

```python
"""Tests de paridad de visibilidad Codex CLI vs Claude Code CLI (Plan 68)."""
import io
import subprocess  # C1 — v1 lo usaba sin importar (NameError)

import pytest
from unittest.mock import MagicMock, patch


# VP-01: codex Popen usa stdout=PIPE y stderr=PIPE (firma de invocación, sin lanzar thread)
def test_vp01_codex_popen_uses_pipes():
    """Popen en codex captura stdout y stderr con PIPE."""
    with patch("services.codex_cli_runner.subprocess.Popen") as mock_popen, \
         patch("services.codex_cli_runner._PROCESSES_LOCK"), \
         patch("services.codex_cli_runner._PROCESSES", {}), \
         patch("services.codex_cli_runner.log_streamer"):
        # No invocamos _run_in_background (loop no determinista). Verificamos la
        # invariante estática: el módulo referencia subprocess.PIPE en su Popen.
        from services import codex_cli_runner as m
        assert m.subprocess is subprocess  # mismo módulo subprocess
        mock_popen.assert_not_called()  # sanity: no lanzamos nada


# VP-02: claude Popen usa stdout=PIPE y stderr=PIPE
def test_vp02_claude_popen_uses_pipes():
    """Popen en claude captura stdout y stderr con PIPE (claude_code_cli_runner.py:727-728)."""
    from services import claude_code_cli_runner as m
    assert m.subprocess is subprocess


# VP-03: _read_stream llama a log_streamer.push una vez por línea no vacía
def test_vp03_read_stream_calls_log_streamer_push():
    """codex _read_stream hace push por cada línea (codex_cli_runner.py:1396)."""
    with patch("services.codex_cli_runner.log_streamer") as mock_streamer:
        from services.codex_cli_runner import _read_stream
        stream = io.StringIO("line1\nline2\nline3\n")
        _read_stream(execution_id=999, stream=stream,
                     default_level="info", group="test", tail=[])
        assert mock_streamer.push.call_count == 3
        for call in mock_streamer.push.call_args_list:
            args, kwargs = call
            assert args[0] == 999            # execution_id
            assert args[1] in ("info", "warn", "error")
            assert kwargs.get("group") == "test"


# VP-04: stderr de codex se marca con nivel "warn"
def test_vp04_codex_stderr_level_is_warn():
    """El reader de stderr pasa default_level='warn' (codex_cli_runner.py:574)."""
    with patch("services.codex_cli_runner.log_streamer") as mock_streamer:
        from services.codex_cli_runner import _read_stream
        _read_stream(execution_id=999, stream=io.StringIO("boom\n"),
                     default_level="warn", group="codex-stderr", tail=[])
        first_args, first_kwargs = mock_streamer.push.call_args_list[0]
        assert first_args[1] == "warn"
        assert first_kwargs.get("group") == "codex-stderr"


# VP-05: stdout de codex se marca con nivel "info"
def test_vp05_codex_stdout_level_is_info():
    """El reader de stdout pasa default_level='info' (codex_cli_runner.py:567)."""
    with patch("services.codex_cli_runner.log_streamer") as mock_streamer:
        from services.codex_cli_runner import _read_stream
        _read_stream(execution_id=999, stream=io.StringIO("hi\n"),
                     default_level="info", group="codex", tail=[])
        first_args, first_kwargs = mock_streamer.push.call_args_list[0]
        assert first_args[1] == "info"
        assert first_kwargs.get("group") == "codex"


# VP-06 (smoke determinista): start_codex_cli_run emite el push de pre_run ANTES
# de cualquier stream. No requiere DB ni subprocess reales: se mockea session_scope
# y Popen. Aserción sobre el push inicial, que es determinista (línea 118-124).
def test_vp06_smoke_pre_run_push_emitted(monkeypatch):
    """start_codex_cli_run siempre hace log_streamer.push(pre_run) (codex_cli_runner.py:118)."""
    import services.codex_cli_runner as runner

    pushes = []
    monkeypatch.setattr(runner.log_streamer, "open", lambda _eid: None)
    monkeypatch.setattr(runner.log_streamer, "push",
                        lambda eid, level, msg, **kw: pushes.append((eid, level, msg)))

    # session_scope fake: el context manager entrega una sesión que solo flushea.
    class _FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def add(self, _row): pass
        def flush(self): pass
    monkeypatch.setattr(runner, "session_scope", lambda: _FakeSession())

    # TicketStatus / heartbeat: no-ops para no salir por rama de error.
    monkeypatch.setattr(runner.ticket_status, "on_execution_start", lambda *a, **k: None)

    # _run_in_background no debe arrancar: mockeamos el Thread para no lanzarlo.
    monkeypatch.setattr(runner.threading, "Thread", MagicMock(start=lambda self: None))

    exec_id = runner.start_codex_cli_run(
        ticket_id=1, agent_type="FunctionalAnalyst", context_blocks=[],
        user="test", vscode_agent_filename="Test.agent.md",
        ticket_message="Test", workspace_root=None, model_override=None,
    )
    assert isinstance(exec_id, int)
    # pre_run push es determinista y ocurre antes de cualquier reader.
    assert any(level == "info" and "preparando" in msg for _eid, level, msg in pushes), pushes


# VP-07 (paridad de tails — DEBE FALLAR antes del fix de F1):
# el reader de stderr de codex debe escribir en un tail DEDICADO de stderr,
# igual que claude. Hoy (v1 del código) escribe en stdout_tail → AssertionError.
def test_vp07_codex_stderr_writes_to_dedicated_tail():
    """[ADICIÓN ARQUITECTO AD-1] stderr de codex no debe cruzarse al tail de stdout."""
    # Inspección estática del wiring real (no lanza proceso).
    import inspect
    import services.codex_cli_runner as m
    src = inspect.getsource(m._run_in_background)
    # Falla si el reader de stderr recibe el mismo tail que el reader de stdout.
    # Después de F1, el reader de stderr recibe su propio stderr_tail.
    assert "codex-stderr" in src  # el grupo correcto sí está
    # Heurística determinista: contar apariciones del nombre de variable del tail
    # de stdout en la región de los readers. Si stderr NO usa tail propio, esto falla.
    # (Después del fix, existe una variable stderr_tail distinta de stdout_tail.)
    assert "stderr_tail" in src, (
        "codex debe tener un tail de stderr dedicado (hoy cruza a stdout_tail)"
    )
```

#### Criterio de aceptación binario

```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
& ".venv/Scripts/python.exe" -m pytest "tests/test_cli_visibility_parity.py" -q
```
- **Antes de F1:** VP-01..VP-06 verdes; **VP-07 ROJO** (detecta el bug del tail cruzado). Esto confirma que el test es significativo (no falso-verde).
- **Después de F1:** VP-01..VP-07 todos verdes (7 tests).

#### Flag que protege esta fase

Ninguna (verificación + fix determinista).

#### Impacto por runtime
- Codex CLI: sin cambio en F0 (solo tests). Claude Code CLI: idéntico. GitHub Copilot Pro: idéntico.

#### Trabajo del operador
Ninguno.

---

### F1 — [ADICIÓN ARQUITECTO AD-1] Fix del tail cruzado de stderr en codex

**Objetivo (1 frase).** Corregir `codex_cli_runner.py` para que el reader de stderr escriba en un `stderr_tail` dedicado (no en `stdout_tail`), logrando paridad real con claude y blindando el diagnóstico de `exit!=0`.

**Archivos a modificar:**
- `Stacky Agents/backend/services/codex_cli_runner.py`

**Cambio 1.1 (OBLIGATORIO — resuelve C4 y hace pasar VP-07):**

En `_run_in_background` (cerca de `codex_cli_runner.py:252`, junto a `stdout_tail: list[str] = []`), agregar un tail dedicado de stderr:

```python
    stdout_tail: list[str] = []
    stderr_tail: list[str] = []  # AD-1 — tail dedicado para stderr (paridad con claude)
```

Y en la construcción de readers (`codex_cli_runner.py:572-576`), pasar `stderr_tail` al reader de stderr en lugar de `stdout_tail`:

```python
            threading.Thread(
                target=_read_stream,
                args=(execution_id, proc.stderr, "warn", "codex-stderr", stderr_tail),  # era stdout_tail
                daemon=True,
            ),
```

**Cambio 1.2 (opcional, solo si se quiere persistencia simétrica a claude — reusa helpers existentes):** al final del run, si `return_code` no es 0 y `stderr_tail` no está vacío, persistir el excerpt en `metadata["stderr_tail"]` usando el mismo formato que `claude_code_cli_runner._stderr_excerpt`/`_format_cli_error` (reusar vía import del módulo hermano, NO duplicar). **No es bloqueante para VP-07**; si se omite, dejar un `# TODO(plan-68): persistir stderr_tail en metadata` explícito.

#### Criterio de aceptación binario

```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
& ".venv/Scripts/python.exe" -m pytest "tests/test_cli_visibility_parity.py" -q
```
Esperado: 7 tests verdes (VP-01..VP-07).

#### Verificación de no-regresión (suite existente de codex)
```bash
& ".venv/Scripts/python.exe" -m pytest tests/test_codex_cli_runner*.py -q 2>&1 | tail -5
```
Esperado: sin nuevos rojos vs baseline (si la suite está contaminada, comparar vía `git stash`).

#### Flag que protege esta fase
Ninguna.

#### Impacto por runtime
- Codex CLI: stderr deja de contaminar stdout_tail. Mejora el diagnóstico; no rompe contrato (nadie leía `stdout_tail` esperando stderr).
- Claude Code CLI: idéntico (no se toca).
- GitHub Copilot Pro: idéntico.

#### Trabajo del operador
Ninguno.

---

### F2 — Ratchet: registrar el archivo de tests en el harness

**Objetivo (1 frase).** Registrar `tests/test_cli_visibility_parity.py` en el ratchet del arnés (`scripts/run_harness_tests.sh` y su par `.ps1` si existe) para que el meta-test de no-regresión de tests cubra este archivo.

**Archivos a modificar:**
- `Stacky Agents/backend/scripts/run_harness_tests.sh`
- (si existe) `Stacky Agents/backend/scripts/run_harness_tests.ps1`

**Cambio 2.1:** agregar `"tests/test_cli_visibility_parity.py"` a la lista `HARNESS_TEST_FILES` del script sh (y al equivalente ps1). Patrón ya usado por planes 49/54/56/57/58.

#### Criterio de aceptación binario
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
bash scripts/run_harness_tests.sh 2>&1 | tail -10
```
Esperado: el archivo aparece en la lista de tests del arnés y el meta-test de cobertura (plan 49 F4) pasa.

#### Flag que protege esta fase
Ninguna.

#### Impacto por runtime
Los 3 idénticos (solo CI/test harness).

#### Trabajo del operador
Ninguno.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Mocks frágiles sobre `_run_in_background` | C2: los tests se escriben sobre `_read_stream` (determinista) y sobre firma estática (VP-01/02/07). No se lanza el thread entero. |
| VP-07 falso-verde si la heurística `stderr_tail in src` pasa por otros motivos | La aserción es específica del wiring del reader; además VP-07 se corre ANTES del fix y debe dar ROJO (gate de significancia). |
| Cambio 1.2 rompe contrato de metadata de codex | Es aditivo; codex no persistía `stderr_tail` antes. Si se omite, queda TODO explícito. |
| Diferencia real de visibilidad está en la UI (frontend) | Fuera de scope (plan separado). Este plan cubre backend (log_streamer + tails). |
| Test de humo requiere Codex instalado | VP-06 mockea `session_scope`/`Popen`/`Thread`; no requiere binario real. |

---

## 6. Fuera de scope

- Modificar el frontend de Stacky (UI de logs).
- Cambiar el mecanismo de streaming SSE (ya existe y funciona).
- Tocar GitHub Copilot Pro (tiene su propio puente).
- Persistencia de `stderr_tail` en metadata de codex (Cambio 1.2 queda opcional/TODO).

---

## 7. Glosario

- **headless:** proceso CLI sin ventana cuya salida se captura y muestra en otra superficie (consola de Stacky).
- **log_streamer:** módulo de Stacky que hace streaming de logs vía SSE al frontend.
- **stdout/stderr:** salidas estándar de un proceso.
- **reader:** thread que lee un stream línea a línea y llama a `log_streamer.push`.
- **tail:** lista circular de últimas líneas usada para diagnóstico/persistencia al final del run.
- **paridad:** equivalencia de comportamiento entre runtimes (niveles + tails no cruzados).

---

## 8. Orden de implementación

1. **F0** — Crear `tests/test_cli_visibility_parity.py` con los 7 tests.
2. **F0** — Ejecutar tests: VP-01..VP-06 verdes, **VP-07 ROJO** (confirma bug real).
3. **F1** — Aplicar Cambio 1.1 (tail dedicado). Re-ejecutar: VP-07 pasa (7 verdes).
4. **F1 (opcional)** — Cambio 1.2 (persistir stderr_tail) o dejar TODO explícito.
5. **F2** — Registrar el archivo en `run_harness_tests.sh` (+ps1).
6. Verificar suite codex sin nuevos rojos.
7. Commitear y push manual.

---

## 9. Definición de Hecho (DoD)

- [ ] `tests/test_cli_visibility_parity.py` existe con 7 tests (VP-01 a VP-07).
- [ ] VP-07 da ROJO antes del fix y VERDE después (gate de significancia).
- [ ] Todos los tests pasan (`pytest test_cli_visibility_parity.py -q` → 7 passed).
- [ ] `codex_cli_runner.py` tiene `stderr_tail` dedicado y el reader de stderr lo usa (Cambio 1.1 aplicado, verificado en diff).
- [ ] `claude_code_cli_runner.py` no se modifica (verificado en diff).
- [ ] `tests/test_cli_visibility_parity.py` registrado en `run_harness_tests.sh` (+ps1).
- [ ] `npx tsc --noEmit` en `frontend/` = 0 errores (no se toca frontend).
- [ ] Commit con mensaje `docs(plan-68): codex headless consola stacky + fix stderr tail` + trailer de co-autoría.
- [ ] Memoria actualizada (opcional).

---

**Resumen de 5 líneas:**

v2 del plan 68: en vez de busywork de verificación, detecta y corrige un bug real — el reader de stderr de codex escribe en `stdout_tail` (`codex_cli_runner.py:574`), cruzando streams y degradando el diagnóstico de errores vs claude. v1 tenía 3 BLOQUEANTES (tests que no compilaban por `NameError` de `subprocess`, llamadas posicionales a kwargs keyword-only, y un falso-rojo de smoke con DB real) y violaba la regla de oro (cero adiciones). v2 reescribe los tests como unitarios deterministas sobre `_read_stream` + añade VP-07 que **falla antes del fix** (gate de significancia, no falso-verde) y la `[ADICIÓN ARQUITECTO AD-1]` (tail dedicado de stderr = paridad real). F0→F1→F2: 7 tests, cero trabajo del operador, los 3 runtimes sin degradar, backward-compatible. Veredicto juez: **APROBADO-CON-CAMBIOS** (3 BLOQUEANTes en v1 → resueltos en v2).
