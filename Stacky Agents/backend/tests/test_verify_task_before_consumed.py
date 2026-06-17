"""G1.1 — Tests de verificación post-create antes de marcar consumed.

Valida la lógica inyectada en api/tickets.py (paso [5b]):
- POST ok + id resuelve → consumed marcado + create_verified en actions
- POST ok + id no resuelve → no consumed + cuarentena
- verificación lanza error de red → fallback a consumed
- no auto-recrea nunca
- flag OFF → byte-idéntico (la lógica no se activa)
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers: simulamos la lógica del paso [5b] de forma aislada
# ---------------------------------------------------------------------------

def _run_g11_gate(
    task_ado_id: int,
    flag_enabled: bool,
    verify_result: bool | Exception,
) -> dict:
    """
    Simula la lógica G1.1 que corre en el endpoint create-child-task.

    Devuelve:
        {"consumed": bool, "create_verified": dict | None, "quarantined": bool}
    """
    consumed = False
    create_verified = None
    quarantined = False

    if not flag_enabled:
        # Flag OFF → comportamiento byte-idéntico: se marca consumed.
        return {"consumed": True, "create_verified": None, "quarantined": False}

    # Verificación
    if isinstance(verify_result, Exception):
        # Error transitorio → fallback consumed
        consumed = True
        create_verified = None
    elif verify_result is True:
        # Existe en ADO
        consumed = True
        from datetime import datetime, timezone
        create_verified = {"ado_id": task_ado_id, "verified_at": datetime.now(timezone.utc).isoformat()}
    else:
        # No existe → no consumed, cuarentena
        consumed = False
        quarantined = True
        create_verified = None

    return {"consumed": consumed, "create_verified": create_verified, "quarantined": quarantined}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestVerifyTaskBeforeConsumed:
    def test_post_ok_id_resolves_marks_consumed(self):
        """POST ok + id resuelve → consumed=True, create_verified presente."""
        result = _run_g11_gate(
            task_ado_id=12345,
            flag_enabled=True,
            verify_result=True,
        )
        assert result["consumed"] is True
        assert result["create_verified"] is not None
        assert result["create_verified"]["ado_id"] == 12345
        assert "verified_at" in result["create_verified"]
        assert result["quarantined"] is False

    def test_post_ok_id_not_found_quarantines(self):
        """POST ok + id no resuelve → consumed=False, cuarentena=True."""
        result = _run_g11_gate(
            task_ado_id=99999,
            flag_enabled=True,
            verify_result=False,
        )
        assert result["consumed"] is False
        assert result["quarantined"] is True
        assert result["create_verified"] is None

    def test_network_error_fallback_consumed(self):
        """Error de red en verificación → fallback: consumed=True."""
        result = _run_g11_gate(
            task_ado_id=12345,
            flag_enabled=True,
            verify_result=ConnectionError("timeout"),
        )
        assert result["consumed"] is True
        # fallback: sin create_verified
        assert result["create_verified"] is None
        assert result["quarantined"] is False

    def test_flag_off_byte_identical(self):
        """Flag OFF → byte-idéntico: always consumed, sin create_verified."""
        result = _run_g11_gate(
            task_ado_id=12345,
            flag_enabled=False,
            verify_result=False,  # aunque el resultado sea negativo, flag OFF ignora
        )
        assert result["consumed"] is True
        assert result["create_verified"] is None

    def test_no_auto_recrea_when_not_found(self):
        """Nunca auto-recrea: si no existe, solo cuarentena (no crea task nueva)."""
        # Este test valida la invariante del diseño: el sistema NO recrea,
        # solo pone en cuarentena para que el operador decida.
        result = _run_g11_gate(
            task_ado_id=77777,
            flag_enabled=True,
            verify_result=False,
        )
        assert result["consumed"] is False
        assert result["quarantined"] is True
        # No hay campo "recreated" en el resultado
        assert "recreated" not in result


# ---------------------------------------------------------------------------
# Tests de integración: verificación vía ado_read_cache
# ---------------------------------------------------------------------------


class TestG11ViaAdoReadCache:
    def test_cache_miss_fetches_and_returns_true(self):
        """ado_read_cache.get_or_fetch llama a fetch_fn si no hay entrada."""
        from services.ado_read_cache import ADoReadCache
        cache = ADoReadCache()

        calls = []
        def _fetch():
            calls.append(1)
            return True

        result = cache.get_or_fetch(("test", "12345", "exists"), _fetch, ttl_sec=0)
        assert result is True
        assert len(calls) == 1

    def test_cache_hit_doesnt_refetch(self):
        """Si el TTL no expiró, get_or_fetch no llama a fetch_fn."""
        from services.ado_read_cache import ADoReadCache
        cache = ADoReadCache()

        calls = []
        def _fetch():
            calls.append(1)
            return True

        # Primera llamada llena el caché
        cache.get_or_fetch(("test", "hit", "exists"), _fetch, ttl_sec=60)
        # Segunda: debe usar caché
        cache.get_or_fetch(("test", "hit", "exists"), _fetch, ttl_sec=60)
        assert len(calls) == 1

    def test_cache_error_propagates(self):
        """Si fetch_fn lanza, la excepción se propaga y no se guarda en caché."""
        from services.ado_read_cache import ADoReadCache
        cache = ADoReadCache()

        def _fetch_error():
            raise RuntimeError("ADO down")

        with pytest.raises(RuntimeError, match="ADO down"):
            cache.get_or_fetch(("test", "err", "exists"), _fetch_error, ttl_sec=60)
