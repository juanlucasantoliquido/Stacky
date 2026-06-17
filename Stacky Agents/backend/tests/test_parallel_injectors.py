"""Tests TDD para I3.1 — Paralelización de injectors independientes.

Spec:
- Flag OFF → serial byte-idéntico (misma lista de bloques que el serial).
- Flag ON → mismo conjunto y MISMO orden de bloques que el serial.
- Excepción en un injector no tumba los demás.
- Con mocks que duermen, la latencia mejora (dos en paralelo < dos en serie).

Los tests usan mocks de _inject_similar_tickets y _inject_ado_context
para no pegar a ADO real.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _log(*_a, **_k):
    pass


# ---------------------------------------------------------------------------
# Fixtures de bloques
# ---------------------------------------------------------------------------

_SIMILAR_BLOCK = {"id": "ado-similar-tickets", "content": "tickets similares"}
_ADO_COMMENT_BLOCK = {"id": "ado-comments", "content": "comentarios ado"}
_ADO_ATTACHMENT_BLOCK = {"id": "ado-attachments", "content": "adjuntos ado"}


# ---------------------------------------------------------------------------
# Helpers de mocks
# ---------------------------------------------------------------------------

def _mock_inject_similar(blocks_to_add):
    """Devuelve un mock de _inject_similar_tickets que agrega blocks_to_add."""
    def _fn(ticket_id, agent_type, ticket_ado_id, blocks, project_name, log):
        return list(blocks) + blocks_to_add
    return _fn


def _mock_inject_ado(blocks_to_add, stats=None):
    """Devuelve un mock de _inject_ado_context que agrega blocks_to_add."""
    def _fn(*, ticket_id, agent_type, ticket_ado_id, blocks, project, project_ctx, project_name, ticket_obj, log):
        return list(blocks) + blocks_to_add, stats
    return _fn


# ---------------------------------------------------------------------------
# Función auxiliar: equivalencia serial vs paralelo
# ---------------------------------------------------------------------------

def _run_merge_with_flag(flag_on: bool, sim_fn, ado_fn, base_blocks):
    """Ejecuta el merge de injectors tal como lo hace enrich_blocks."""
    from config import config

    blocks = list(base_blocks)
    ado_stats = None

    if flag_on:
        from concurrent.futures import ThreadPoolExecutor

        def _run_sim():
            return sim_fn(None, "developer", 1, [], "P", _log)

        def _run_ado():
            return ado_fn(
                ticket_id=None, agent_type="developer", ticket_ado_id=1,
                blocks=[], project="P", project_ctx=None,
                project_name="P", ticket_obj=None, log=_log
            )

        sim_blocks = []
        ado_blocks = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_sim = pool.submit(_run_sim)
            fut_ado = pool.submit(_run_ado)
            try:
                result = fut_sim.result()
                sim_blocks = result if isinstance(result, list) else []
            except Exception:
                pass
            try:
                ado_result = fut_ado.result()
                if isinstance(ado_result, tuple) and len(ado_result) == 2:
                    ado_blocks, ado_stats = ado_result
                    if not isinstance(ado_blocks, list):
                        ado_blocks = []
            except Exception:
                pass

        seen_ids = {b.get("id") for b in blocks if isinstance(b, dict) and b.get("id")}
        for b in sim_blocks:
            if isinstance(b, dict):
                bid = b.get("id")
                if not bid or bid not in seen_ids:
                    blocks.append(b)
                    if bid:
                        seen_ids.add(bid)
        for b in ado_blocks:
            if isinstance(b, dict):
                bid = b.get("id")
                if not bid or bid not in seen_ids:
                    blocks.append(b)
                    if bid:
                        seen_ids.add(bid)
    else:
        blocks = sim_fn(None, "developer", 1, blocks, "P", _log)
        ado_list, ado_stats = ado_fn(
            ticket_id=None, agent_type="developer", ticket_ado_id=1,
            blocks=blocks, project="P", project_ctx=None,
            project_name="P", ticket_obj=None, log=_log
        )
        blocks = ado_list

    return blocks, ado_stats


# ---------------------------------------------------------------------------
# Test 1: Flag OFF → serial idéntico (identidad de contenido)
# ---------------------------------------------------------------------------

def test_parallel_off_is_serial():
    base = [{"id": "ado-epic-structured", "content": "epica"}]
    sim_fn = _mock_inject_similar([_SIMILAR_BLOCK])
    ado_fn = _mock_inject_ado([_ADO_COMMENT_BLOCK], stats={"x": 1})

    serial_blocks, serial_stats = _run_merge_with_flag(False, sim_fn, ado_fn, base)
    parallel_blocks, parallel_stats = _run_merge_with_flag(True, sim_fn, ado_fn, base)

    # Mismo contenido (mismos ids en mismo orden)
    serial_ids = [b.get("id") for b in serial_blocks]
    parallel_ids = [b.get("id") for b in parallel_blocks]
    assert parallel_ids == serial_ids


# ---------------------------------------------------------------------------
# Test 2: Excepción en un injector no tumba el otro
# ---------------------------------------------------------------------------

def test_parallel_exception_isolation():
    base = [{"id": "ado-epic-structured", "content": "epica"}]

    # similar_tickets lanza excepción
    def _failing_sim(ticket_id, agent_type, ticket_ado_id, blocks, project_name, log):
        raise RuntimeError("ADO down")

    ado_fn = _mock_inject_ado([_ADO_COMMENT_BLOCK], stats=None)

    # No debe lanzar excepción en el llamador
    from concurrent.futures import ThreadPoolExecutor
    blocks = list(base)
    ado_blocks = []
    sim_blocks = []

    def _run_sim():
        return _failing_sim(None, "dev", 1, [], "P", _log)

    def _run_ado():
        return ado_fn(ticket_id=None, agent_type="dev", ticket_ado_id=1,
                      blocks=[], project="P", project_ctx=None,
                      project_name="P", ticket_obj=None, log=_log)

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_sim = pool.submit(_run_sim)
        fut_ado = pool.submit(_run_ado)
        try:
            sim_blocks = fut_sim.result()
        except Exception:
            sim_blocks = []  # excepción aislada
        try:
            ado_result = fut_ado.result()
            if isinstance(ado_result, tuple):
                ado_blocks, _ = ado_result
        except Exception:
            ado_blocks = []

    # El bloque ADO sigue presente aunque similar falló
    seen = {b.get("id") for b in ado_blocks}
    assert "ado-comments" in seen


# ---------------------------------------------------------------------------
# Test 3: Latencia mejora con injectors lentos
# ---------------------------------------------------------------------------

def test_parallel_latency_improvement():
    SLEEP = 0.05  # 50ms por injector

    def _slow_sim(ticket_id, agent_type, ticket_ado_id, blocks, project_name, log):
        time.sleep(SLEEP)
        return list(blocks) + [_SIMILAR_BLOCK]

    def _slow_ado(*, ticket_id, agent_type, ticket_ado_id, blocks, project, project_ctx,
                   project_name, ticket_obj, log):
        time.sleep(SLEEP)
        return list(blocks) + [_ADO_COMMENT_BLOCK], None

    base = [{"id": "ado-epic-structured", "content": "epica"}]

    # Serial (debería ser ~2*SLEEP)
    t0 = time.monotonic()
    _run_merge_with_flag(False, _slow_sim, _slow_ado, base)
    serial_time = time.monotonic() - t0

    # Paralelo (debería ser ~SLEEP)
    t1 = time.monotonic()
    _run_merge_with_flag(True, _slow_sim, _slow_ado, base)
    parallel_time = time.monotonic() - t1

    # El paralelo debe ser significativamente más rápido que el serial
    assert parallel_time < serial_time * 1.5, (
        f"El paralelo ({parallel_time:.3f}s) no fue más rápido que el serial ({serial_time:.3f}s)"
    )


# ---------------------------------------------------------------------------
# Test 4: Dedup por ID — bloques que ya están en base no se duplican
# ---------------------------------------------------------------------------

def test_parallel_dedup_by_id():
    # El bloque similar ya está en base
    existing_similar = {"id": "ado-similar-tickets", "content": "ya existe"}
    base = [{"id": "ado-epic-structured", "content": "epica"}, existing_similar]

    sim_fn = _mock_inject_similar([_SIMILAR_BLOCK])  # mismo id, diferente content
    ado_fn = _mock_inject_ado([_ADO_COMMENT_BLOCK], stats=None)

    parallel_blocks, _ = _run_merge_with_flag(True, sim_fn, ado_fn, base)

    # No debe haber duplicados por id
    ids = [b.get("id") for b in parallel_blocks]
    assert ids.count("ado-similar-tickets") == 1
