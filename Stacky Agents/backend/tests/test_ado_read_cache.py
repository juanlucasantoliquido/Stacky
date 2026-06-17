"""Tests TDD para I3.2 — Caché en memoria de lecturas ADO.

Spec:
- TTL 0 → sin caché, fetch_fn siempre se llama (byte-idéntico).
- TTL > 0 → segunda llamada con el mismo key dentro del TTL NO llama a fetch_fn.
- Entrada expirada → fetch_fn se vuelve a llamar.
- invalidate(ado_id) invalida todas las entradas con key[1] == str(ado_id).
- is_warm(key) → True si existe y no expiró.
- Fallo de fetch_fn → excepción se propaga, caché no se corrompe.
- Thread-safety básica: N threads concurrentes no corrompen el estado.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.ado_read_cache import ADoReadCache


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _counter_fn(result="DATA"):
    """Devuelve (fn, call_count_ref) donde call_count_ref[0] se incrementa."""
    calls = [0]

    def _fn():
        calls[0] += 1
        return result

    return _fn, calls


# ---------------------------------------------------------------------------
# Test 1: TTL 0 → siempre llama a fetch_fn (no-op caché)
# ---------------------------------------------------------------------------

def test_ttl_zero_always_fetches():
    cache = ADoReadCache()
    fn, calls = _counter_fn("X")
    key = ("proj", "42", "similar")

    r1 = cache.get_or_fetch(key, fn, ttl_sec=0)
    r2 = cache.get_or_fetch(key, fn, ttl_sec=0)

    assert r1 == "X"
    assert r2 == "X"
    assert calls[0] == 2  # llamada en cada invocación


# ---------------------------------------------------------------------------
# Test 2: Hit dentro del TTL → fetch_fn no se llama en segunda vuelta
# ---------------------------------------------------------------------------

def test_cache_hit_within_ttl():
    cache = ADoReadCache()
    fn, calls = _counter_fn("DATA")
    key = ("proj", "7", "ado_context")

    r1 = cache.get_or_fetch(key, fn, ttl_sec=60)
    r2 = cache.get_or_fetch(key, fn, ttl_sec=60)

    assert r1 == r2 == "DATA"
    assert calls[0] == 1  # solo una llamada


# ---------------------------------------------------------------------------
# Test 3: Entrada expirada → nueva llamada a fetch_fn
# ---------------------------------------------------------------------------

def test_expired_entry_refetches():
    cache = ADoReadCache()
    fn, calls = _counter_fn("FRESH")
    key = ("proj", "99", "similar")

    # TTL muy corto
    cache.get_or_fetch(key, fn, ttl_sec=1)
    time.sleep(1.05)  # esperar expiración
    cache.get_or_fetch(key, fn, ttl_sec=1)

    assert calls[0] == 2


# ---------------------------------------------------------------------------
# Test 4: invalidate(ado_id) invalida todas las entradas del ado_id
# ---------------------------------------------------------------------------

def test_invalidate_by_ado_id():
    cache = ADoReadCache()
    fn_sim, calls_sim = _counter_fn("SIM")
    fn_ado, calls_ado = _counter_fn("ADO")
    fn_other, calls_other = _counter_fn("OTHER")

    key_sim = ("proj", "5", "similar")
    key_ado = ("proj", "5", "ado_context")
    key_other = ("proj", "99", "similar")  # otro ado_id

    cache.get_or_fetch(key_sim, fn_sim, 60)
    cache.get_or_fetch(key_ado, fn_ado, 60)
    cache.get_or_fetch(key_other, fn_other, 60)

    # Invalidar solo ado_id=5
    cache.invalidate("5")

    # Las entradas de ado_id=5 deben haber sido invalidadas
    cache.get_or_fetch(key_sim, fn_sim, 60)
    cache.get_or_fetch(key_ado, fn_ado, 60)
    # La entrada de ado_id=99 NO debe haber sido invalidada
    cache.get_or_fetch(key_other, fn_other, 60)

    assert calls_sim[0] == 2   # re-fetched
    assert calls_ado[0] == 2   # re-fetched
    assert calls_other[0] == 1  # NOT re-fetched (ado_id diferente)


# ---------------------------------------------------------------------------
# Test 5: invalidate() con int funciona igual que con str
# ---------------------------------------------------------------------------

def test_invalidate_accepts_int():
    cache = ADoReadCache()
    fn, calls = _counter_fn("V")
    key = ("proj", "10", "similar")

    cache.get_or_fetch(key, fn, 60)
    cache.invalidate(10)  # int, no str
    cache.get_or_fetch(key, fn, 60)

    assert calls[0] == 2


# ---------------------------------------------------------------------------
# Test 6: is_warm() refleja estado correcto
# ---------------------------------------------------------------------------

def test_is_warm():
    cache = ADoReadCache()
    fn, _ = _counter_fn("W")
    key = ("proj", "3", "similar")

    assert not cache.is_warm(key)
    cache.get_or_fetch(key, fn, 60)
    assert cache.is_warm(key)
    cache.invalidate("3")
    assert not cache.is_warm(key)


# ---------------------------------------------------------------------------
# Test 7: Fallo de fetch_fn → excepción propagada, caché sin corrupción
# ---------------------------------------------------------------------------

def test_failed_fetch_does_not_corrupt_cache():
    cache = ADoReadCache()
    calls = [0]

    def _failing():
        calls[0] += 1
        raise RuntimeError("ADO down")

    fn_ok, calls_ok = _counter_fn("OK")
    key_fail = ("proj", "1", "similar")
    key_ok = ("proj", "2", "similar")

    # La primera falla
    try:
        cache.get_or_fetch(key_fail, _failing, 60)
        assert False, "debería haber lanzado"
    except RuntimeError:
        pass

    # El caché para key_fail no quedó sucio
    assert not cache.is_warm(key_fail)
    assert calls[0] == 1

    # Otro key funciona bien
    cache.get_or_fetch(key_ok, fn_ok, 60)
    assert cache.is_warm(key_ok)


# ---------------------------------------------------------------------------
# Test 8: Thread-safety básica — N threads concurrentes no corrompen el caché
# ---------------------------------------------------------------------------

def test_thread_safety():
    cache = ADoReadCache()
    results: list = []
    errors: list = []

    def _work(n: int):
        try:
            fn, _ = _counter_fn(f"T{n}")
            key = ("proj", str(n % 3), "similar")
            val = cache.get_or_fetch(key, fn, 10)
            results.append(val)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=_work, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(results) == 20


# ---------------------------------------------------------------------------
# Test 9: clear() vacía el caché completamente
# ---------------------------------------------------------------------------

def test_clear():
    cache = ADoReadCache()
    fn, calls = _counter_fn("C")
    key = ("proj", "7", "similar")

    cache.get_or_fetch(key, fn, 60)
    assert cache.is_warm(key)
    cache.clear()
    assert not cache.is_warm(key)
    cache.get_or_fetch(key, fn, 60)
    assert calls[0] == 2
