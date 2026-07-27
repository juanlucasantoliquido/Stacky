"""Plan 254 F3 — endurecer y MEDIR el drenaje del stream que YA existe.

C1 (crítica adversarial): el v1 partía de un diagnóstico FALSO. El drenaje no
hay que crearlo — `claude_code_cli_runner.py` ya hace
`for reader in readers: reader.join(timeout=5)` apenas sale del bucle de
`proc.wait()`, y `_classify_run_outcome` recién corre ~300 líneas después.
Lo que faltaba: timeout configurable, deadline COMPARTIDO y detección de
vencimiento (`drain_timed_out`).

C12: la causa de la anomalía de E1 (eventos del stream DESPUÉS del cierre) no
estaba probada. `test_discrimina_h_a_de_h_b` produce el dato en vez de asumirlo:
  H-a → el join venció y los threads daemon siguen vivos  → drain_timed_out True
  H-b → el reader terminó y el log se volcó tarde         → drain_timed_out False

Estos tests ejercitan el BLOQUE de drenaje (deadline compartido sobre una lista
de threads) exactamente como está escrito en el runner, sin levantar un CLI real.
"""
from __future__ import annotations

import os
import sys
import threading
import time as _time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.run_outcome import classify_outcome_reason  # noqa: E402


def _drain(readers: list[threading.Thread], timeout_s: float) -> bool:
    """Réplica EXACTA del bloque de `claude_code_cli_runner.py` (F3).

    Deadline COMPARTIDO entre todos los readers (no `timeout_s` por thread).
    Devuelve `drain_timed_out`.
    """
    deadline = _time.monotonic() + timeout_s
    timed_out = False
    for reader in readers:
        remaining = max(0.0, deadline - _time.monotonic())
        reader.join(timeout=remaining)
        if reader.is_alive():
            timed_out = True
    return timed_out


def _reader_que_emite_tarde(flag: list[bool], delay: float) -> threading.Thread:
    """Lector que emite su `result ok` DESPUÉS de que el proceso murió."""
    def _run():
        _time.sleep(delay)
        flag[0] = True

    return threading.Thread(target=_run, daemon=True)


def _reader_colgado(stop: threading.Event) -> threading.Thread:
    """Lector que nunca termina solo (pipe colgado / nieto con el pipe abierto)."""
    return threading.Thread(target=lambda: stop.wait(30), daemon=True)


def test_drain_espera_eventos_en_vuelo():
    """Un `result ok` que llega tarde tiene que estar VISIBLE al clasificar."""
    result_ok = [False]
    reader = _reader_que_emite_tarde(result_ok, 0.5)
    reader.start()

    timed_out = _drain([reader], timeout_s=15.0)

    assert timed_out is False
    assert result_ok[0] is True, "el drenaje no esperó al evento en vuelo"
    # Y el clasificador, que corre DESPUÉS del join, ya ve el valor actualizado.
    assert classify_outcome_reason(
        return_code=1, result_ok_seen=result_ok[0]
    ) == "dirty_exit_after_work"


def test_drain_respeta_timeout_y_marca_drain_timed_out():
    stop = threading.Event()
    reader = _reader_colgado(stop)
    reader.start()
    try:
        t0 = _time.monotonic()
        timed_out = _drain([reader], timeout_s=1.0)
        elapsed = _time.monotonic() - t0
    finally:
        stop.set()

    assert timed_out is True, "el drenaje vencido no quedó marcado"
    assert 0.9 <= elapsed < 3.0, f"no cortó en el timeout configurado ({elapsed:.2f}s)"


def test_drain_deadline_es_compartido_entre_los_dos_readers():
    """Con 2 lectores colgados y timeout=2, el bloque tarda ~2 s, NO ~4."""
    stop = threading.Event()
    readers = [_reader_colgado(stop), _reader_colgado(stop)]
    for r in readers:
        r.start()
    try:
        t0 = _time.monotonic()
        timed_out = _drain(readers, timeout_s=2.0)
        elapsed = _time.monotonic() - t0
    finally:
        stop.set()

    assert timed_out is True
    assert elapsed < 3.5, (
        f"el deadline NO es compartido: {elapsed:.2f}s (2 readers x 2s = 4s)"
    )


def test_result_ok_tardio_evita_el_falso_rojo():
    """Integración del bug real del 07-25: rc=1 + `result ok` a +0,3 s."""
    result_ok = [False]
    readers = [_reader_que_emite_tarde(result_ok, 0.3), _reader_que_emite_tarde([False], 0.1)]
    for r in readers:
        r.start()

    drain_timed_out = _drain(readers, timeout_s=15.0)
    return_code = 1  # "claude code cli exited with code 1"

    reason = classify_outcome_reason(
        return_code=return_code, result_ok_seen=result_ok[0],
    )
    assert drain_timed_out is False
    assert reason == "dirty_exit_after_work", (
        "sin drenar, el desenlace sería 'cli_failure' → el FALSO ROJO"
    )
    # Y el estado propuesto NO es un verde automático: lo mira un humano.
    from services.run_outcome import outcome_reason_to_status
    assert outcome_reason_to_status(reason) == "needs_review"


def test_discrimina_h_a_de_h_b():
    """C12 — convierte una hipótesis en un DATO consultable por metadata."""
    # H-a: el lector sigue vivo tras vencer el join.
    stop = threading.Event()
    vivo = _reader_colgado(stop)
    vivo.start()
    try:
        h_a = _drain([vivo], timeout_s=0.5)
    finally:
        stop.set()

    # H-b: el lector TERMINÓ antes del join (su log se volcó tarde, otro problema).
    muerto = _reader_que_emite_tarde([False], 0.0)
    muerto.start()
    muerto.join(timeout=5)
    h_b = _drain([muerto], timeout_s=0.5)

    assert h_a is True
    assert h_b is False
    assert h_a != h_b, "H-a y H-b no son distinguibles por metadata"


def test_el_runner_usa_deadline_compartido_y_flag_configurable():
    """Centinela del cableado REAL: el bloque del runner no puede regresionar
    al `join(timeout=5)` hardcodeado ni perder la marca `drain_timed_out`."""
    fuente = (ROOT / "services" / "claude_code_cli_runner.py").read_text(encoding="utf-8")
    assert "STACKY_CLI_STREAM_DRAIN_TIMEOUT_S" in fuente
    assert "_drain_deadline" in fuente
    assert "_drain_timed_out" in fuente
    assert "reader.join(timeout=5)" not in fuente, "volvió el timeout hardcodeado"
