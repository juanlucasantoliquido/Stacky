"""Plan 208 F0 — Flags + dispatcher de completación (infra compartida).

Verifica que ambas flags estén declaradas/categorizadas/curadas con default ON,
y que el dispatcher encole O(1) sin lanzar, registre su post-hook y arranque una
sola vez.
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_KEY_SYNC = "STACKY_ADO_SYNC_ON_COMPLETION_ENABLED"
_KEY_MATRIX = "STACKY_ADO_STATE_MATRIX_ENABLED"


def _drain(q) -> list:
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


def test_flags_registradas_y_default_on():
    from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS
    from config import config as cfg
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    by_key = {s.key: s for s in FLAG_REGISTRY}
    for key in (_KEY_SYNC, _KEY_MATRIX):
        assert key in by_key, f"{key} no está en FLAG_REGISTRY"
        assert by_key[key].type == "bool"
        assert by_key[key].default is True, f"{key} debe ser default ON"
        assert by_key[key].env_only is False, f"{key} debe ser editable por UI"
        assert key in _CURATED_DEFAULTS_ON, f"{key} falta en _CURATED_DEFAULTS_ON"
        assert getattr(cfg, key) is True, f"config.{key} debe ser True por default"

    assert _KEY_MATRIX in _CATEGORY_KEYS["flujo_funcional"]
    assert _KEY_SYNC in _CATEGORY_KEYS["fiabilidad_ciclo_vida"]


def test_enqueue_no_lanza_con_flags_off(monkeypatch):
    from config import config as cfg
    from services import completion_dispatcher as cd

    monkeypatch.setattr(cfg, _KEY_SYNC, False, raising=False)
    monkeypatch.setattr(cfg, _KEY_MATRIX, False, raising=False)
    _drain(cd._Q)

    cd.enqueue_completion(ticket_id=1, execution_id=2, final_status="completed",
                          agent_type="developer")

    assert cd._Q.empty(), "con ambas flags OFF no debe encolarse nada"


def test_register_agrega_post_hook():
    from services import completion_dispatcher as cd

    captured = []
    cd.register(captured.append)

    assert len(captured) == 1
    assert callable(captured[0])
    assert getattr(captured[0], "__name__", "") == "_post_hook"


def test_post_hook_encola_evento(monkeypatch):
    from config import config as cfg
    from services import completion_dispatcher as cd

    monkeypatch.setattr(cfg, _KEY_SYNC, False, raising=False)
    monkeypatch.setattr(cfg, _KEY_MATRIX, True, raising=False)
    _drain(cd._Q)

    cd._post_hook(ticket_id=11, execution_id=22, final_status="completed",
                  agent_type="developer", error=None)

    items = _drain(cd._Q)
    assert len(items) == 1
    assert items[0] == {
        "ticket_id": 11, "execution_id": 22,
        "final_status": "completed", "agent_type": "developer",
    }


def test_start_idempotente():
    from services import completion_dispatcher as cd

    def _count() -> int:
        return sum(1 for t in threading.enumerate() if t.name == "completion-dispatcher")

    cd.start()
    after_first = _count()
    cd.start()
    after_second = _count()

    assert after_first == 1, f"start() debe dejar exactamente 1 hilo, hay {after_first}"
    assert after_second == after_first, "start() repetido no debe arrancar otro hilo"
