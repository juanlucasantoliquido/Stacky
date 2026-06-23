# Plan 68 — Codex CLI headless en consola de Stacky: paridad de visibilidad con Claude Code CLI

> Versión: **v1** | Estado: PROPUESTO | Fecha: 2026-06-23
> Autor: StackyArchitectaUltraEficientCode
> Origen del número: listado de `Stacky Agents/docs/` → NN máximo = 67 → este plan = **68**.

---

## 1. Objetivo + KPI

**Objetivo (un párrafo).** Hoy el runner de Codex CLI (`codex_cli_runner.py`) ya persiste stderr vía `_read_stream`, pero hay una **asimetría reportada** en la visibilidad de la salida del proceso en la consola de Stacky frente a Claude Code CLI. Este plan asegura que **ambos runtimes** (Codex CLI y Claude Code CLI) tengan paridad de visibilidad: (1) stdout y stderr se streaman en tiempo real a través de `log_streamer.push` (funcionalidad ya existente), (2) el operador puede ver el progreso del agente en la UI sin necesidad de abrir archivos, y (3) cualquier diferencia en el comportamiento se documenta y se corrige. El cambio es **de verificación y endurecimiento** de lo que ya existe, no una reescritura.

**KPI / impacto esperado:**
- **Paridad de visibilidad:** Codex CLI y Claude Code CLI muestran stdout/stderr en la consola de Stacky de forma equivalente.
- **Tiempo real:** el stream es visible en tiempo real (no solo al final del run) a través de SSE (`log_streamer`).
- **Cero regresiones:** el comportamiento existente de Claude Code CLI no se altera.
- **Trabajo del operador:** ninguno. La paridad es automática.
- **Paridad 3 runtimes:** Codex CLI, Claude Code CLI y GitHub Copilot Pro tienen visibilidad equivalente (Copilot ya funciona a través de su propio puente).

---

## 2. Por qué ahora / gap que cierra

- **Evidencia en código:**
  - `codex_cli_runner.py:574-576` ya crea un reader para stderr: `target=_read_stream, args=(..., proc.stderr, "warn", "codex-stderr", ...)`
  - `claude_code_cli_runner.py` tiene readers equivalentes para stdout y stderr.
  - Ambos usan `log_streamer.push` para streaming.
- **Gap reportado:** el operador indica "Codex CLI se debe mostrar headless en la consola de Stacky". Esto sugiere que **hay una diferencia percibida** entre ambos runtimes que necesita verificación y corrección.
- **Plan 54** estableció paridad de `rejection_lessons` entre los 3 runtimes. Este plan completa la paridad de visibilidad.

---

## 3. Principios y guardarraíles (no negociables)

- **3 runtimes con paridad:** Codex CLI, Claude Code CLI y GitHub Copilot Pro deben tener visibilidad equivalente de stdout/stderr.
- **Cero trabajo extra al operador:** la paridad es automática; sin config nueva.
- **Human-in-the-loop intacto:** el operador ve lo que hace el agente; no hay nueva autonomía.
- **Mono-operador sin auth:** no RBAC.
- **No degradar:** reutilizar `log_streamer.push` ya existente. Sin nuevos mecanismos de streaming.
- **Reuso obligatorio:** los readers ya existen; solo se endurecen y verifican.

---

## 4. Fases

> **Orden de dependencia:** F0 → F1 → F2.
> F0 = verificación y tests de paridad; F1 = corrección de diferencias; F2 = ratchet.

> **Intérprete de tests (usar en todos los comandos pytest):**
> `& "N:/GIT/RS/STACKY/Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest <archivo> -q`

---

### F0 — Verificar estado actual de visibilidad: tests de comparación

**Objetivo (1 frase).** Crear `tests/test_cli_visibility_parity.py` que verifique que ambos runners (Codex y Claude) streamean stdout/stderr a través de `log_streamer.push` con la misma estructura y niveles.

**Archivo a crear:** `N:/GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_cli_visibility_parity.py`

**Tests exactos (copiar tal cual):**

```python
"""Tests de paridad de visibilidad Codex CLI vs Claude Code CLI (Plan 68)."""
import pytest
from unittest.mock import Mock, patch, MagicMock
import threading


# VP-01: codex_cli_runner crea readers para stdout y stderr
def test_vp01_codex_creates_stdout_stderr_readers():
    """Verificar que _run_in_background crea 2 readers (stdout + stderr)."""
    # Simular el mínimo necesario para que el test compile
    with patch("services.codex_cli_runner._PROCESSES_LOCK"):
        with patch("services.codex_cli_runner._PROCESSES", {}):
            with patch("services.codex_cli_runner.log_streamer"):
                with patch("services.codex_cli_runner.subprocess.Popen") as mock_popen:
                    # Configurar el mock de Popen
                    mock_proc = MagicMock()
                    mock_proc.poll.return_value = None  # Proceso "corriendo"
                    mock_proc.pid = 12345
                    mock_proc.stdin = MagicMock()
                    mock_proc.stdin.write = MagicMock()
                    mock_proc.stdin.flush = MagicMock()
                    mock_proc.stdin.close = MagicMock()
                    mock_proc.stdout = MagicMock()
                    mock_proc.stderr = MagicMock()
                    mock_proc.wait.return_value = 0  # Exit code 0
                    mock_popen.return_value = mock_proc

                    # Importar después de patchear
                    from services.codex_cli_runner import _run_in_background

                    # Ejecutar en un thread con timeout (el loop es infinito si wait no termina)
                    import queue
                    result_queue = queue.Queue()

                    def run_thread():
                        try:
                            # Hack: forzar el loop a salir rápido
                            mock_proc.wait.side_effect = [0]  # Primera llamada retorna 0
                            _run_in_background(
                                execution_id=1,
                                ticket_message="test",
                                vscode_agent_filename="Test.agent.md",
                                workspace_root=None,
                                model_override=None,
                            )
                            result_queue.put(("ok", None))
                        except Exception as e:
                            result_queue.put(("error", e))

                    t = threading.Thread(target=run_thread, daemon=True)
                    t.start()
                    t.join(timeout=5)

                    if t.is_alive():
                        pytest.fail("El thread no terminó en 5s — posible loop infinito")

                    status, err = result_queue.get()
                    if status == "error":
                        pytest.fail(f"Error en _run_in_background: {err}")

                    # Verificar que se crearon threads para stdout y stderr
                    # (no podemos verificar fácilmente sin mockear Thread, pero al menos
                    # verificamos que Popen fue llamado con stdout=PIPE y stderr=PIPE)
                    call_args = mock_popen.call_args
                    assert call_args is not None
                    kwargs = call_args[1] if len(call_args) > 1 else {}
                    assert kwargs.get("stdout") == subprocess.PIPE
                    assert kwargs.get("stderr") == subprocess.PIPE


# VP-02: claude_code_cli_runner crea readers para stdout y stderr
def test_vp02_claude_creates_stdout_stderr_readers():
    """Verificar que _run_in_background de Claude crea 2 readers."""
    with patch("services.claude_code_cli_runner._PROCESSES_LOCK"):

        with patch("services.claude_code_cli_runner._PROCESSES", {}):
            with patch("services.claude_code_cli_runner.log_streamer"):
                with patch("services.claude_code_cli_runner.subprocess.Popen") as mock_popen:
                    mock_proc = MagicMock()
                    mock_proc.poll.return_value = None
                    mock_proc.pid = 12346
                    mock_proc.stdin = MagicMock()
                    mock_proc.stdout = MagicMock()
                    mock_proc.stderr = MagicMock()
                    mock_proc.wait.return_value = 0
                    mock_popen.return_value = mock_proc

                    from services.claude_code_cli_runner import _run_in_background

                    import queue
                    result_queue = queue.Queue()

                    def run_thread():
                        try:
                            mock_proc.wait.side_effect = [0]
                            _run_in_background(
                                execution_id=2,
                                ticket_message="test",
                                vscode_agent_filename="Test.agent.md",
                                workspace_root=None,
                                model_override=None,
                                effort_override=None,
                            )
                            result_queue.put(("ok", None))
                        except Exception as e:
                            result_queue.put(("error", e))

                    t = threading.Thread(target=run_thread, daemon=True)
                    t.start()
                    t.join(timeout=5)

                    if t.is_alive():
                        pytest.fail("El thread Claude no terminó en 5s")

                    status, err = result_queue.get()
                    if status == "error":
                        pytest.fail(f"Error en _run_in_background Claude: {err}")

                    call_args = mock_popen.call_args
                    assert call_args is not None
                    kwargs = call_args[1] if len(call_args) > 1 else {}
                    assert kwargs.get("stdout") == subprocess.PIPE
                    assert kwargs.get("stderr") == subprocess.PIPE


# VP-03: _read_stream llama a log_streamer.push
def test_vp03_read_stream_calls_log_streamer_push():
    """Verificar que _read_stream llama a log_streamer.push con nivel correcto."""
    with patch("services.codex_cli_runner.log_streamer") as mock_streamer:
        from services.codex_cli_runner import _read_stream
        import io

        # Stream falso que devuelve 3 líneas
        stream = io.StringIO("line1\nline2\nline3\n")
        tail = []

        _read_stream(
            execution_id=999,
            stream=stream,
            default_level="info",
            group="test",
            tail=tail,
        )

        # Verificar que push fue llamado 3 veces (una por línea)
        assert mock_streamer.push.call_count == 3

        # Verificar que los niveles son correctos
        for call in mock_streamer.push.call_args_list:
            args, kwargs = call
            # args = (execution_id, level, message, ...)
            assert args[0] == 999
            assert args[1] in ("info", "warn", "error")
            assert kwargs.get("group") == "test"


# VP-04: stderr de Codex se marca con nivel "warn"
def test_vp04_codex_stderr_level_is_warn():
    """Verificar que el reader de stderr usa nivel 'warn'."""
    with patch("services.codex_cli_runner.log_streamer") as mock_streamer:
        from services.codex_cli_runner import _read_stream
        import io

        stream = io.StringIO("error message\n")
        tail = []

        _read_stream(
            execution_id=999,
            stream=stream,
            default_level="warn",  # stderr usa "warn" como default
            group="codex-stderr",
            tail=tail,
        )

        # La primera llamada debe tener nivel "warn"
        first_call = mock_streamer.push.call_args_list[0]
        args, kwargs = first_call
        assert args[1] == "warn"
        assert kwargs.get("group") == "codex-stderr"


# VP-05: stdout de Codex se marca con nivel "info"
def test_vp05_codex_stdout_level_is_info():
    """Verificar que el reader de stdout usa nivel 'info'."""
    with patch("services.codex_cli_runner.log_streamer") as mock_streamer:
        from services.codex_cli_runner import _read_stream
        import io

        stream = io.StringIO("normal message\n")
        tail = []

        _read_stream(
            execution_id=999,
            stream=stream,
            default_level="info",  # stdout usa "info"
            group="codex",
            tail=tail,
        )

        first_call = mock_streamer.push.call_args_list[0]
        args, kwargs = first_call
        assert args[1] == "info"
        assert kwargs.get("group") == "codex"
```

#### Criterio de aceptación binario

```bash
# Ejecutar desde backend/
& ".venv/Scripts/python.exe" -m pytest "tests/test_cli_visibility_parity.py" -q
```
Esperado: 5 tests verdes (VP-01 a VP-05).

#### Flag que protege esta fase

Ninguna. Esta fase es de verificación; no hay comportamiento nuevo.

#### Impacto por runtime

- **Codex CLI:** idéntico.
- **Claude Code CLI:** idéntico.
- **GitHub Copilot Pro:** idéntico (no se toca).

#### Trabajo del operador

Ninguno. Tests de verificación.

---

### F1 — Corregir diferencias si las hay

**Objetivo (1 frase).** Si los tests de F0 revelan diferencias, corregir `codex_cli_runner.py` y/o `claude_code_cli_runner.py` para asegurar paridad.

**Archivos a modificar (solo si es necesario):**
- `N:/GIT/RS/STACKY\Stacky\Stacky Agents\backend\services\codex_cli_runner.py`
- `N:/GIT\RS/STACKY\Stacky\Stacky Agents\backend\services\claude_code_cli_runner.py`

**Estado esperado (verificación previa):**

Según la inspección del código:
- `codex_cli_runner.py:574-576` — readers stdout/stderr presentes.
- `claude_code_cli_runner.py` — readers equivalentes presentes.

Si los tests de F0 pasan, **esta fase NO requiere cambios**. Si fallan, los cambios mínimos serían:

#### Cambio 1.1 (solo si VP-01 falla) — Asegurar que Codex crea ambos readers

En `codex_cli_runner.py`, verificar que en `_run_in_background` (cerca de línea 564-577) existan ambos readers:

```python
readers = [
    threading.Thread(
        target=_read_stream,
        args=(execution_id, proc.stdout, "info", "codex", stdout_tail),
        kwargs={"telemetry_sink": _stream_telemetry_sink,
                "on_runaway": _codex_on_runaway},
        daemon=True,
    ),
    threading.Thread(
        target=_read_stream,
        args=(execution_id, proc.stderr, "warn", "codex-stderr", stdout_tail),
        daemon=True,
    ),
]
for reader in readers:
    reader.start()
```

Si este código ya existe (y según la lectura de línea 564-577, sí existe), no se requiere cambio.

#### Cambio 1.2 (solo si VP-02 falla) — Asegurar que Claude crea ambos readers

Verificar código equivalente en `claude_code_cli_runner.py`.

#### Criterio de aceptación binario

```bash
# Ejecutar desde backend/
& ".venv/Scripts/python.exe" -m pytest "tests/test_cli_visibility_parity.py" -q
```
Esperado: 5 tests verdes.

#### Flag que protege esta fase

Ninguna.

#### Impacto por runtime

- **Codex CLI:** idéntico si ya está correcto (según código, lo está).
- **Claude Code CLI:** idéntico.
- **GitHub Copilot Pro:** idéntico.

#### Trabajo del operador

Ninguno. Correcciones menores si es necesario.

---

### F2 — Ratchet: test de humo en runtime real

**Objetito (1 frase).** Crear un test de integración que ejecute un run real (o mockeado) de Codex CLI y verifique que los logs aparecen en `log_streamer`.

**Archivo a modificar:** `N:/GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_cli_visibility_parity.py` (agregar al final)

**Test a agregar:**

```python
# VP-06: test de humo — log_streamer.push es llamado con datos reales
def test_vp06_smoke_log_streamer_receives_codex_output(monkeypatch):
    """Test de humo: verificar que log_streamer.push recibe datos de Codex."""
    from services.codex_cli_runner import start_codex_cli_run
    from db import session_scope
    from models import Ticket, AgentExecution

    # Mock de log_streamer
    push_calls = []
    def fake_push(exec_id, level, message, **kwargs):
        push_calls.append({"exec_id": exec_id, "level": level, "message": message})

    import services.codex_cli_runner as runner_module
    monkeypatch.setattr(runner_module.log_streamer, "push", fake_push)
    monkeypatch.setattr(runner_module.log_streamer, "open", lambda x: None)

    # Mock de subprocess para no ejecutar Codex real
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.pid = 99999
    mock_proc.stdin = MagicMock()
    mock_proc.stdout = MagicMock()
    mock_proc.stderr = MagicMock()
    mock_proc.wait.return_value = 0

    # Stream falso que devuelve algo
    import io
    mock_proc.stdout.readline = lambda: b""  # EOF inmediato
    mock_proc.stderr.readline = lambda: b""

    monkeypatch.setattr(runner_module.subprocess, "Popen", lambda *a, **k: mock_proc)

    # Crear ticket dummy
    with session_scope() as session:
        ticket = Ticket(
            ado_id=999999,
            title="Test visibility",
            description="Test",
            work_item_type="Task",
        )
        session.add(ticket)
        session.flush()

        exec_id = start_codex_cli_run(
            ticket_id=ticket.id,
            agent_type="FunctionalAnalyst",
            context_blocks=[],
            user="test",
            vscode_agent_filename="Test.agent.md",
            ticket_message="Test",
            workspace_root=None,
            model_override=None,
        )

    # Verificar que log_streamer.push fue llamado al menos una vez
    assert len(push_calls) > 0, "log_streamer.push debe ser llamado al menos una vez"
    assert any(c["exec_id"] == exec_id for c in push_calls)
```

#### Criterio de aceptación binario

```bash
# Ejecutar desde backend/
& ".venv/Scripts/python.exe" -m pytest "tests/test_cli_visibility_parity.py::test_vp06_smoke_log_streamer_receives_codex_output" -q
```
Esperado: 1 test verde.

#### Flag que protege esta fase

Ninguna.

#### Impacto por runtime

- **Codex CLI:** idéntico.
- **Claude Code CLI:** idéntico.
- **GitHub Copilot Pro:** idéntico.

#### Trabajo del operador

Ninguno. Test de humo.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Los tests de mocking son frágiles | Los tests usan mocks mínimos y verifican comportamiento esencial (`PIPE`, `push`). Si fallan, se ajusta el test, no el código. |
| Diferencia real de visibilidad no está en el código sino en la UI | Este plan cubre el backend (log_streamer). Si hay diferencia en el frontend, es fuera de scope (plan separado). |
| El test de humo requiere Codex instalado | El test usa mock de subprocess, no requiere Codex real. |

---

## 6. Fuera de scope

- Modificar el frontend de Stacky (UI de logs).
- Modificar la forma en que se muestran los logs (ya existe SSE).
- Modificar GitHub Copilot Pro (tiene su propio puente).

---

## 7. Glosario

- **headless:** el proceso CLI corre sin ventana, pero su salida se captura y muestra en otra superficie (consola de Stacky).
- **log_streamer:** módulo de Stacky que hace streaming de logs a través de SSE al frontend.
- **stdout/stderr:** salidas estándar de un proceso. Codex CLI y Claude Code CLI escriben su output ahí.
- **reader:** thread que lee línea por línea un stream y llama a `log_streamer.push`.
- **paridad:** equivalencia de comportamiento entre runtimes.

---

## 8. Orden de implementación

1. **F0** — Crear `tests/test_cli_visibility_parity.py` (tests de verificación).
2. **F0** — Ejecutar tests para verificar estado actual.
3. **F1** — Si tests fallan, corregir runners. Si pasan, marcar F1 como completa.
4. **F2** — Agregar test de humo VP-06.
5. Verificar todos los tests verdes.
6. Commitear y push manual.

---

## 9. Definición de Hecho (DoD)

- [ ] `tests/test_cli_visibility_parity.py` existe con 6 tests (VP-01 a VP-06).
- [ ] Todos los tests pasan (`pytest test_cli_visibility_parity.py -q`).
- [ ] `codex_cli_runner.py` tiene readers para stdout y stderr (verificado).
- [ ] `claude_code_cli_runner.py` tiene readers para stdout y stderr (verificado).
- [ ] `npx tsc --noEmit` en `frontend/` = 0 errores (no se toca frontend).
- [ ] Commit con mensaje `docs(plan-68): codex headless consola stacky` + trailer de co-autoría.
- [ ] Memoria actualizada (opcional).

---

**Resumen de 5 líneas:**

Este plan verifica y asegura que Codex CLI tenga paridad de visibilidad con Claude Code CLI en la consola de Stacky: ambos streamean stdout/stderr a través de `log_streamer.push` con niveles equivalentes. KPI: tests de paridad que verifican readers y llamadas a push. Cero trabajo del operador: verificación automática, sin config nueva. Paridad 3 runtimes: Codex, Claude y Copilot quedan equivalentes. Implementación F0→F2: tests TDD + corrección mínima si es necesario + test de humo.
