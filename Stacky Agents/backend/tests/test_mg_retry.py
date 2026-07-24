"""tests/test_mg_retry.py — Plan 217 Batch 5, F8 (§9, C2).

Valida `tools/migrar_mantis_gitlab/retry.py`:
  - `with_backoff` reintenta y eventualmente tiene éxito.
  - agota `max_retries` y re-lanza la excepción original.
  - excepciones no reintentables (ej. `ValueError` sin patrón 5xx) se
    re-lanzan de inmediato, sin reintentar.
  - `sleep_fn` inyectado no duerme de verdad (no depende de mockear el
    módulo `time` global).
  - `rate_limit_pause` delega en `sleep_fn`.
  - `CircuitBreaker` abre tras N fallos consecutivos y se resetea tras un
    éxito.

Prohibición dura verificada acá también (import-scan): este módulo NO
importa `services.gitlab_client`/`services.gitlab_provider`.
"""
from __future__ import annotations

import pytest

from tools.migrar_mantis_gitlab.retry import CircuitBreaker, rate_limit_pause, with_backoff


class _FakeSleep:
    """`sleep_fn` inyectable: no duerme de verdad, solo registra las
    pausas pedidas — así el test no depende de mockear `time.sleep`
    global (mandato del batch)."""

    def __init__(self) -> None:
        self.calls: "list[float]" = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


# ── with_backoff: reintenta y eventualmente tiene éxito ─────────────────


def test_with_backoff_reintenta_y_eventualmente_tiene_exito():
    sleep = _FakeSleep()
    attempts = {"count": 0}

    def _flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ConnectionError("boom de red")
        return "ok"

    result = with_backoff(
        _flaky, max_retries=5, backoff_seconds=[0.1, 0.2, 0.3], sleep_fn=sleep,
    )

    assert result == "ok"
    assert attempts["count"] == 3
    assert sleep.calls == [0.1, 0.2]  # 2 reintentos antes del éxito en el 3er intento


def test_with_backoff_detecta_5xx_en_mensaje_de_excepcion_generica():
    sleep = _FakeSleep()
    attempts = {"count": 0}

    def _flaky_5xx():
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("GitLab respondió 503 Service Unavailable")
        return "ok"

    result = with_backoff(_flaky_5xx, max_retries=3, backoff_seconds=[0.1], sleep_fn=sleep)

    assert result == "ok"
    assert attempts["count"] == 2
    assert sleep.calls == [0.1]


# ── with_backoff: agota max_retries y re-lanza la excepción original ────


def test_with_backoff_agota_max_retries_y_relanza_excepcion_original():
    sleep = _FakeSleep()

    def _always_fails():
        raise TimeoutError("timeout de red persistente")

    with pytest.raises(TimeoutError, match="timeout de red persistente"):
        with_backoff(_always_fails, max_retries=3, backoff_seconds=[0.1, 0.2], sleep_fn=sleep)

    # 3 reintentos -> 3 pausas (backoff_seconds se agota, repite el último valor)
    assert sleep.calls == [0.1, 0.2, 0.2]


# ── excepciones no reintentables se re-lanzan de inmediato ──────────────


def test_with_backoff_no_reintenta_excepciones_no_reintentables():
    sleep = _FakeSleep()
    attempts = {"count": 0}

    def _auth_error():
        attempts["count"] += 1
        raise ValueError("401 Unauthorized")  # no matchea \b5\d{2}\b

    with pytest.raises(ValueError, match="401 Unauthorized"):
        with_backoff(_auth_error, max_retries=5, backoff_seconds=[0.1], sleep_fn=sleep)

    assert attempts["count"] == 1  # ni un solo reintento
    assert sleep.calls == []


def test_with_backoff_max_retries_cero_no_reintenta():
    sleep = _FakeSleep()

    def _fails_once():
        raise ConnectionError("boom")

    with pytest.raises(ConnectionError):
        with_backoff(_fails_once, max_retries=0, backoff_seconds=[1.0], sleep_fn=sleep)

    assert sleep.calls == []


# ── rate_limit_pause delega en sleep_fn, no duerme de verdad ────────────


def test_rate_limit_pause_delega_en_sleep_fn_sin_dormir_de_verdad():
    sleep = _FakeSleep()

    rate_limit_pause(2.5, sleep_fn=sleep)

    assert sleep.calls == [2.5]


# ── CircuitBreaker ────────────────────────────────────────────────────────


def test_circuit_breaker_abre_tras_n_fallos_consecutivos():
    breaker = CircuitBreaker(threshold=3)

    assert breaker.is_open is False
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.is_open is False
    breaker.record_failure()
    assert breaker.is_open is True


def test_circuit_breaker_se_resetea_tras_un_exito():
    breaker = CircuitBreaker(threshold=3)
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.is_open is True

    breaker.record_success()

    assert breaker.is_open is False


def test_circuit_breaker_default_threshold_es_10():
    breaker = CircuitBreaker()
    assert breaker.threshold == 10
    for _ in range(9):
        breaker.record_failure()
    assert breaker.is_open is False
    breaker.record_failure()
    assert breaker.is_open is True


# ── prohibición dura: retry.py no importa el cliente/provider compartido ─


def test_retry_module_no_importa_gitlab_client_ni_provider():
    import ast

    import tools.migrar_mantis_gitlab.retry as retry_module

    source = open(retry_module.__file__, encoding="utf-8").read()
    tree = ast.parse(source)

    imported_modules: "list[str]" = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)

    assert not any("gitlab_client" in m for m in imported_modules)
    assert not any("gitlab_provider" in m for m in imported_modules)
