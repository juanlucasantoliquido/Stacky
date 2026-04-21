"""Tests del sweeper anti-zombies de AgentQueue."""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

from agent_queue import AgentQueue


@pytest.fixture
def state_file_with_zombie(tmp_path):
    """State con un ticket cuyo invoking_pid apunta a un proceso muerto."""
    state_dir = tmp_path / "pipeline"
    state_dir.mkdir()
    state_path = state_dir / "state.json"
    # PID muy alto (no existe) — pipeline_state.is_invoke_still_valid lo detecta
    state = {
        "tickets": {
            "ZOMBIE-1": {
                "estado":             "dev_en_proceso",
                "invoking_pid":       9999999,
                "invoke_started_at":  "2020-01-01T00:00:00",
                "invoke_ttl_minutes": 1,
                "invoke_host":        "localhost",
            }
        },
        "last_run": None,
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")
    return state_path


@pytest.fixture
def state_file_with_live_ticket(tmp_path):
    """State con un ticket cuyo invoking_pid es el proceso actual (vivo)."""
    state_dir = tmp_path / "pipeline"
    state_dir.mkdir()
    state_path = state_dir / "state.json"
    state = {
        "tickets": {
            "LIVE-1": {
                "estado":             "dev_en_proceso",
                "invoking_pid":       os.getpid(),
                "invoke_started_at":  "2099-01-01T00:00:00",  # TTL lejano
                "invoke_ttl_minutes": 999999,
                "invoke_host":        "localhost",
            }
        },
        "last_run": None,
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")
    return state_path


class TestZombieSweeper:
    def test_libera_slot_de_proceso_muerto(self, state_file_with_zombie):
        # sweep_interval alto para que NO corra automáticamente durante el test
        aq = AgentQueue(slots_dev=1, state_path=str(state_file_with_zombie),
                        zombie_sweep_interval=3600.0)
        # Simular que el slot está ocupado por el ticket zombie
        with aq._lock:
            aq._active["dev"].append("ZOMBIE-1")

        reaped = aq.sweep_zombies()

        assert ("dev", "ZOMBIE-1") in reaped
        assert "ZOMBIE-1" not in aq._active["dev"]
        assert aq._stats["zombies_reaped"] == 1
        aq.shutdown()

    def test_no_libera_ticket_con_proceso_vivo(self, state_file_with_live_ticket):
        aq = AgentQueue(slots_dev=1, state_path=str(state_file_with_live_ticket),
                        zombie_sweep_interval=3600.0)
        with aq._lock:
            aq._active["dev"].append("LIVE-1")

        reaped = aq.sweep_zombies()

        assert reaped == []
        assert "LIVE-1" in aq._active["dev"]
        assert aq._stats["zombies_reaped"] == 0
        aq.shutdown()

    def test_dead_letter_tras_max_retries(self, state_file_with_zombie):
        aq = AgentQueue(slots_dev=1, state_path=str(state_file_with_zombie),
                        zombie_sweep_interval=3600.0, max_zombie_retries=2)
        # Simular 3 ciclos del mismo zombie
        for _ in range(3):
            with aq._lock:
                aq._active["dev"].append("ZOMBIE-1")
            # Recargar state (sweeper consume state cada vez)
            with open(state_file_with_zombie, "r", encoding="utf-8") as f:
                state = json.load(f)
            state["tickets"]["ZOMBIE-1"]["estado"] = "dev_en_proceso"
            state["tickets"]["ZOMBIE-1"]["invoking_pid"] = 9999999
            with open(state_file_with_zombie, "w", encoding="utf-8") as f:
                json.dump(state, f)
            aq.sweep_zombies()

        assert aq._stats["zombies_reaped"] == 3
        assert aq._stats["zombie_dead_letters"] >= 1
        aq.shutdown()

    def test_sweep_es_noop_sin_state_path(self):
        aq = AgentQueue(slots_dev=1, state_path=None, zombie_sweep_interval=3600.0)
        with aq._lock:
            aq._active["dev"].append("X")
        assert aq.sweep_zombies() == []
        assert "X" in aq._active["dev"]
        aq.shutdown()

    def test_cola_fluye_tras_reap(self, state_file_with_zombie, monkeypatch):
        """La cola acepta nuevos tickets después de liberar zombie."""
        aq = AgentQueue(slots_dev=1, state_path=str(state_file_with_zombie),
                        zombie_sweep_interval=3600.0)
        with aq._lock:
            aq._active["dev"].append("ZOMBIE-1")
        assert aq.is_busy("dev") is True

        aq.sweep_zombies()

        assert aq.is_busy("dev") is False
        # Submit nuevo y verificar encolado
        done = []
        aq.submit("NEW-1", "dev", callback=lambda: done.append(1))
        # Esperar breve que el worker tome el callback
        for _ in range(50):
            if done:
                break
            time.sleep(0.05)
        assert done == [1]
        aq.shutdown()
