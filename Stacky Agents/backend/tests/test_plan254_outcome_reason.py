"""Plan 254 F2 — taxonomía de desenlaces (`outcome_reason`).

Seis causas radicalmente distintas (cuota agotada, repo ausente, sesión ociosa
tras entregar, timeout del reaper, heartbeat viejo, fallo real del CLI) hoy
colapsan al mismo `error` en la UI. El operador no puede distinguir "me quedé
sin cuota" de "el código no compila", y son acciones OPUESTAS.

`services/run_outcome.py` es un módulo PURO: sin DB, sin red, sin imports de
`db`/`models`. Se testea sin base.
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.run_outcome import (  # noqa: E402
    OUTCOME_REASONS,
    classify_outcome_reason,
    is_operator_actionable,
    outcome_reason_to_status,
)
from services.status_vocabulary import VALID_TICKET_STATUSES  # noqa: E402


def test_clean_exit():
    assert classify_outcome_reason(return_code=0) == "clean_exit"


def test_quota_exhausted_desde_stderr():
    """String EXACTO del log del 07-18 (8 ocurrencias)."""
    texto = "result(error): You've hit your session limit · resets 5:Nam (America/Buenos_Aires)"
    assert classify_outcome_reason(return_code=1, stderr_excerpt=texto) == "quota_exhausted"
    # También desde el último result del stream, no solo desde stderr.
    assert classify_outcome_reason(return_code=1, last_result_text=texto) == "quota_exhausted"


def test_dirty_exit_after_work_mapea_a_needs_review():
    """La regla clave: trabajo entregado + cierre sucio NO es 'completed' automático."""
    reason = classify_outcome_reason(return_code=1, result_ok_seen=True)
    assert reason == "dirty_exit_after_work"
    assert outcome_reason_to_status(reason) == "needs_review"
    assert outcome_reason_to_status(reason) != "completed"
    # El ticket ya terminal cuenta como evidencia de trabajo entregado.
    assert classify_outcome_reason(
        return_code=1, ticket_already_terminal=True
    ) == "dirty_exit_after_work"


def test_stall_no_work_mapea_a_error():
    reason = classify_outcome_reason(return_code=1, stall_fired=True)
    assert reason == "stall_no_work"
    assert outcome_reason_to_status(reason) == "error"
    # Con trabajo previo el watchdog NO es un fallo real.
    assert classify_outcome_reason(
        return_code=1, stall_fired=True, result_ok_seen=True
    ) == "stall_after_work"


def test_preflight_blocked_desde_repo_missing():
    reason = classify_outcome_reason(return_code=None, preflight_block="repo_missing")
    assert reason == "preflight_blocked"
    assert outcome_reason_to_status(reason) == "error"


def test_reaper_timeout_y_heartbeat_son_distintos():
    """11 `reaper[timeout_guardian]` y 8 `reaper[manual] heartbeat_stale` en los logs."""
    assert classify_outcome_reason(
        return_code=None, reaper_kind="timeout_guardian"
    ) == "reaper_timeout"
    assert classify_outcome_reason(
        return_code=None, reaper_kind="manual"
    ) == "reaper_heartbeat"
    assert classify_outcome_reason(
        return_code=None, reaper_kind="heartbeat_stale"
    ) == "reaper_heartbeat"


def test_cli_failure_es_actionable_y_quota_no():
    assert classify_outcome_reason(return_code=1) == "cli_failure"
    assert is_operator_actionable("cli_failure") is True
    assert is_operator_actionable("quota_exhausted") is False
    # Un reason futuro: mejor molestar que ocultar.
    assert is_operator_actionable("reason_del_futuro") is True


def test_precedencia_preflight_gana_a_reaper_y_a_quota():
    """Sin este test el orden de las reglas queda librado al implementador."""
    assert classify_outcome_reason(
        return_code=1,
        preflight_block="repo_missing",
        reaper_kind="timeout_guardian",
        stderr_excerpt="You've hit your session limit",
        stall_fired=True,
        result_ok_seen=True,
    ) == "preflight_blocked"
    # Sin preflight, el reaper le gana a la cuota.
    assert classify_outcome_reason(
        return_code=1,
        reaper_kind="timeout_guardian",
        stderr_excerpt="You've hit your session limit",
    ) == "reaper_timeout"
    # Sin reaper, la cuota le gana al stall.
    assert classify_outcome_reason(
        return_code=1, stall_fired=True, stderr_excerpt="rate limit reached",
    ) == "quota_exhausted"


def test_toda_combinacion_devuelve_un_reason_valido():
    """Grilla exhaustiva de las 8 entradas: nunca None, nunca string libre."""
    grid = itertools.product(
        (None, 0, 1),                       # return_code
        (False, True),                      # result_ok_seen
        (False, True),                      # stall_fired
        ("", "boom"),                       # stderr_excerpt
        ("", "quota"),                      # last_result_text
        (False, True),                      # ticket_already_terminal
        (None, "", "timeout_guardian", "manual"),   # reaper_kind
        (None, "", "repo_missing"),         # preflight_block
    )
    count = 0
    for rc, ok, stall, err, last, term, reaper, pre in grid:
        reason = classify_outcome_reason(
            return_code=rc,
            result_ok_seen=ok,
            stall_fired=stall,
            stderr_excerpt=err,
            last_result_text=last,
            ticket_already_terminal=term,
            reaper_kind=reaper,
            preflight_block=pre,
        )
        assert reason in OUTCOME_REASONS, f"reason inválido {reason!r}"
        count += 1
    assert count == 3 * 2 * 2 * 2 * 2 * 2 * 4 * 3


def test_outcome_reason_to_status_solo_devuelve_estados_validos():
    """C3 — impide que el mapa devuelva un 'published' fantasma."""
    assert len(OUTCOME_REASONS) == 9
    for reason in OUTCOME_REASONS:
        estado = outcome_reason_to_status(reason)
        assert estado in VALID_TICKET_STATUSES, f"{reason} → {estado!r} no existe"
    # Un reason desconocido tampoco puede devolver basura.
    assert outcome_reason_to_status("reason_del_futuro") in VALID_TICKET_STATUSES


def test_modulo_es_puro():
    """Sin DB, sin red: run_outcome no importa db/models ni requests."""
    import services.run_outcome as ro

    fuente = Path(ro.__file__).read_text(encoding="utf-8")
    for prohibido in ("from db import", "import db", "from models import", "requests"):
        assert prohibido not in fuente, f"run_outcome importa {prohibido!r}: ya no es puro"
