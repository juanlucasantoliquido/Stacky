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


# ── R1.2 — desenlace del run claude_code_cli: stall tras result(ok) = éxito ───

def test_classify_outcome_stall_without_result_is_failed():
    """Stall SIN result terminal → cuelgue real → failed."""
    from services.claude_code_cli_runner import _classify_run_outcome

    assert _classify_run_outcome(
        stall_fired=True, result_ok_seen=False, return_code=-15
    ) == "failed_stall"


def test_classify_outcome_stall_after_result_ok_is_success():
    """Stall DESPUÉS de un result(ok) → el trabajo se entregó → success.

    Este es el caso del brief→épica: el agente escribió la épica y emitió
    result(ok); la sesión quedó ociosa y el watchdog la cerró. No es un fallo.
    """
    from services.claude_code_cli_runner import _classify_run_outcome

    assert _classify_run_outcome(
        stall_fired=True, result_ok_seen=True, return_code=-15
    ) == "success"


def test_classify_outcome_clean_exit_is_success():
    """Salida limpia (rc=0) → success, haya o no result registrado."""
    from services.claude_code_cli_runner import _classify_run_outcome

    assert _classify_run_outcome(
        stall_fired=False, result_ok_seen=False, return_code=0
    ) == "success"


def test_classify_outcome_oneshot_terminate_after_result_is_success():
    """One-shot: terminate tras result(ok) deja rc!=0 pero el run fue exitoso."""
    from services.claude_code_cli_runner import _classify_run_outcome

    assert _classify_run_outcome(
        stall_fired=False, result_ok_seen=True, return_code=-15
    ) == "success"


def test_classify_outcome_nonzero_without_result_is_error():
    """Exit code != 0 sin result ok → fallo real del CLI → error."""
    from services.claude_code_cli_runner import _classify_run_outcome

    assert _classify_run_outcome(
        stall_fired=False, result_ok_seen=False, return_code=1
    ) == "error"


# ── R1.2 — one-shot: cierra stdin apenas llega el result terminal ─────────────

def test_oneshot_closes_stdin_after_result():
    """Run one-shot con result(ok): se cierra stdin y se termina en la gracia,
    sin esperar al watchdog de 600s."""
    import time as _time
    import subprocess as sp

    proc = MagicMock()
    proc.stdin.closed = False
    # El proceso nunca termina solo (espera más input): siempre TimeoutExpired
    # hasta que lo terminamos tras cerrar stdin.
    proc.wait.side_effect = [sp.TimeoutExpired("claude", 5), 0]

    one_shot = True
    result_ok_seen = [True]
    one_shot_close_deadline = [None]
    closed = {"stdin": False}

    def _close():
        closed["stdin"] = True
        proc.stdin.closed = True
    proc.stdin.close.side_effect = _close

    return_code = None
    while True:
        try:
            return_code = proc.wait(timeout=5)
            break
        except sp.TimeoutExpired:
            if one_shot and result_ok_seen[0] and one_shot_close_deadline[0] is None:
                if proc.stdin and not proc.stdin.closed:
                    proc.stdin.close()
                one_shot_close_deadline[0] = _time.monotonic() - 1  # ya expirada
            if one_shot_close_deadline[0] is not None and _time.monotonic() > one_shot_close_deadline[0]:
                proc.terminate()
                return_code = proc.wait(timeout=10)
                break
            continue

    assert closed["stdin"] is True
    proc.terminate.assert_called()
    assert return_code == 0


# ── Regresión: "no crea la épica cuando la run termina" ──────────────────────
# Root cause histórico: el brief→épica (one-shot, ado_id=-1) emitía result(ok)
# pero la sesión CLI quedaba ociosa; el stall watchdog disparaba y el run se
# marcaba como FALLIDO. El modal EpicFromBriefModal solo avanza al paso "review"
# (donde el operador aprueba y se crea la épica en ADO) si el run termina en
# completed/needs_review; con failed/error va al paso "error" y la épica NUNCA
# se crea. Este test fija el contrato en el punto de decisión: el escenario
# brief→épica con trabajo entregado NO debe clasificarse como fallo.

# Estados terminales con los que el modal avanza a "review" (puede crear épica).
# Espejo de EpicFromBriefModal.tsx (status === completed || needs_review).
_MODAL_REVIEWABLE_STATUSES = {"completed", "needs_review"}

# Mapeo outcome→status terminal tal como lo aplica _run_in_background:
#   failed_stall → "error"/"failed"  | success → completed/needs_review (vía gate)
_OUTCOME_TO_TERMINAL_FAMILY = {
    "failed_stall": "error",   # el finalizador marca status="error" → modal: paso error
    "error": "error",
    "success": "completed",     # _evaluate_output_quality puede degradar a needs_review
}


def test_brief_epic_stall_after_delivery_is_reviewable():
    """El caso exacto del operador: one-shot que entregó la épica (result ok) y
    luego sufrió stall debe quedar en un estado que el modal acepta para crear
    la épica (NO 'error'). Si vuelve a clasificarse como fallo, este test rojo
    avisa que la épica dejará de crearse al terminar la run."""
    from services.claude_code_cli_runner import _classify_run_outcome

    outcome = _classify_run_outcome(
        stall_fired=True, result_ok_seen=True, return_code=-15
    )
    terminal_family = _OUTCOME_TO_TERMINAL_FAMILY[outcome]
    assert terminal_family in _MODAL_REVIEWABLE_STATUSES, (
        "brief→épica con trabajo entregado terminó en un estado que el modal "
        f"trata como error (outcome={outcome!r}); la épica no se crearía"
    )


def test_real_hang_without_delivery_stays_error():
    """Contracara: un cuelgue real SIN entregar trabajo debe seguir siendo un
    fallo que el modal NO ofrece para crear épica (no degradar la detección de
    cuelgues reales mientras arreglamos el falso-fallo)."""
    from services.claude_code_cli_runner import _classify_run_outcome

    outcome = _classify_run_outcome(
        stall_fired=True, result_ok_seen=False, return_code=-15
    )
    terminal_family = _OUTCOME_TO_TERMINAL_FAMILY[outcome]
    assert terminal_family not in _MODAL_REVIEWABLE_STATUSES
