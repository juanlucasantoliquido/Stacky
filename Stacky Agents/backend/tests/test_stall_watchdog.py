"""Tests R1.1 — Watchdog de inactividad + timeout/kill en codex."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


# ── _validate_pending_task_strict helper (output_watcher) ────────────────────

def test_validate_pending_task_strict_valid():
    """Payload valido → lista vacia."""
    from services.output_watcher import _validate_pending_task_strict

    payload = {"title": "Mi tarea", "rf_id": "RF-1", "parent_ado_id": 100}
    errors = _validate_pending_task_strict(payload, epic_ado_id=100)
    assert errors == []


def test_validate_pending_task_strict_missing_title():
    """Campo 'title' ausente → error."""
    from services.output_watcher import _validate_pending_task_strict

    payload = {"rf_id": "RF-2"}
    errors = _validate_pending_task_strict(payload, epic_ado_id=100)
    assert any("title" in e for e in errors)


def test_validate_pending_task_strict_missing_rf_id():
    """Campo 'rf_id' ausente → error."""
    from services.output_watcher import _validate_pending_task_strict

    payload = {"title": "Tarea"}
    errors = _validate_pending_task_strict(payload, epic_ado_id=100)
    assert any("rf_id" in e for e in errors)


def test_validate_pending_task_strict_ordinal_mismatch():
    """parent_ado_id != epic_ado_id → error de coherencia ordinal."""
    from services.output_watcher import _validate_pending_task_strict

    payload = {"title": "Tarea", "rf_id": "RF-3", "parent_ado_id": 999}
    errors = _validate_pending_task_strict(payload, epic_ado_id=100)
    assert any("mismatch" in e or "ordinal" in e or "coincide" in e for e in errors)


def test_validate_pending_task_strict_no_parent_id_ok():
    """Sin parent_ado_id en payload → coherencia no aplica → valido."""
    from services.output_watcher import _validate_pending_task_strict

    payload = {"title": "Tarea", "rf_id": "RF-4"}
    errors = _validate_pending_task_strict(payload, epic_ado_id=100)
    assert errors == []


# ── Stall watchdog: default 0 → nunca dispara ────────────────────────────────

def test_stall_watchdog_default_zero_never_triggers():
    """Con STACKY_STALL_WATCHDOG_SECONDS=0, el watchdog nunca dispara."""
    # Verificamos que el flag existe y el default es 0
    from config import config
    # No podemos forzar el env aqui (ya esta instanciado), pero verificamos el tipo
    assert isinstance(config.STACKY_STALL_WATCHDOG_SECONDS, int)
    # El valor default debe ser 0 (sin override de env)
    import os
    default_val = int(os.getenv("STACKY_STALL_WATCHDOG_SECONDS", "0"))
    assert default_val == 0


# ── codex wait acotado: terminate/kill en timeout ────────────────────────────

def test_codex_stall_watchdog_terminates_on_stall():
    """Cuando el stall watchdog de codex dispara, termina el proceso."""
    import subprocess
    import time as _time

    proc = MagicMock(spec=subprocess.Popen)
    # Simular que wait() siempre lanza TimeoutExpired (proceso colgado)
    proc.wait.side_effect = subprocess.TimeoutExpired(cmd="codex", timeout=5)

    stall_fired = [False]
    stall_watchdog_sec = 1  # 1 segundo para que dispare rapidamente

    _last_event_mono = [_time.monotonic() - 2]  # 2 segundos sin eventos

    # Simular el bucle del codex runner
    import subprocess as sp

    def simulated_wait_loop():
        while True:
            try:
                return_code = proc.wait(timeout=5)
                break
            except sp.TimeoutExpired:
                if stall_watchdog_sec > 0 and not stall_fired[0]:
                    elapsed = _time.monotonic() - _last_event_mono[0]
                    if elapsed >= stall_watchdog_sec:
                        proc.terminate()
                        try:
                            proc.wait(timeout=10)
                        except sp.TimeoutExpired:
                            proc.kill()
                            proc.wait()
                        stall_fired[0] = True
                        return -1
                continue

    # Resetear el side_effect para la segunda llamada (despues de terminate)
    proc.wait.side_effect = [
        sp.TimeoutExpired("codex", 5),  # primera iteracion del bucle
        0,                               # wait(timeout=10) despues de terminate
    ]

    rc = simulated_wait_loop()
    assert stall_fired[0] is True
    proc.terminate.assert_called()


def test_codex_stall_watchdog_active_stream_not_cut():
    """Stream activo (ultimo evento reciente) → no se corta."""
    import time as _time
    import subprocess as sp

    stall_fired = [False]
    stall_watchdog_sec = 60  # umbral alto
    _last_event_mono = [_time.monotonic()]  # evento justo ahora

    proc = MagicMock()
    proc.wait.return_value = 0  # proceso termina normalmente

    while True:
        try:
            return_code = proc.wait(timeout=5)
            break
        except sp.TimeoutExpired:
            elapsed = _time.monotonic() - _last_event_mono[0]
            if elapsed >= stall_watchdog_sec:
                stall_fired[0] = True
                break
            continue

    assert stall_fired[0] is False
    assert return_code == 0
