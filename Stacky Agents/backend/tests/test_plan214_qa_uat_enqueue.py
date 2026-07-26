"""Plan 214 F3/F4 — Candidato QAUAT al completar el Developer + back-link del veredicto.

El hook SOLO escribe metadata: no publica, no toca ADO, no ejecuta nada salvo que
el operador active el autorun (que corre siempre en dry-run literal).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import db  # noqa: E402

db.init_db()

from services import qa_uat_enqueue as qae  # noqa: E402

_KEY_ON = "STACKY_QA_UAT_ON_DEV_COMPLETE_ENABLED"
_KEY_AUTORUN = "STACKY_QA_UAT_AUTORUN_ENABLED"
_NEXT_ADO = 214000


@pytest.fixture(autouse=True)
def _flags(monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, _KEY_ON, True, raising=False)
    monkeypatch.setattr(cfg, _KEY_AUTORUN, False, raising=False)


@pytest.fixture
def caso():
    """Ticket + ejecución del Developer. Devuelve (ticket_id, execution_id, ado_id)."""
    global _NEXT_ADO
    _NEXT_ADO += 1
    ado_id = _NEXT_ADO

    from db import session_scope
    from models import AgentExecution, Ticket

    creados: list = []

    def _mk(agent_type="developer", metadata=None, con_ado=True):
        with session_scope() as s:
            t = Ticket(ado_id=ado_id if con_ado else None, project="p",
                       stacky_project_name="p", title="t", stacky_status="running")
            if not con_ado:
                t.ado_id = 0
            s.add(t)
            s.flush()
            e = AgentExecution(ticket_id=t.id, agent_type=agent_type, status="completed",
                               input_context_json="[]", started_by="tester")
            if metadata is not None:
                e.metadata_dict = metadata
            s.add(e)
            s.flush()
            creados.append((t.id, e.id))
            return t.id, e.id, ado_id

    yield _mk


def _metadata(execution_id) -> dict:
    from db import session_scope
    from models import AgentExecution

    with session_scope() as s:
        row = s.get(AgentExecution, execution_id)
        return dict(row.metadata_dict or {})


def test_flags_registradas_y_defaults():
    from config import config as cfg
    from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON
    from tests.test_harness_flags_requires import _REQUIRES_MAP_FROZEN

    by_key = {s.key: s for s in FLAG_REGISTRY}
    assert by_key[_KEY_ON].default is True
    # El autorun NO declara `default=`: su type-zero (False) es el default, y así
    # queda fuera del set curado, que es solo para los ON explícitos.
    assert by_key[_KEY_AUTORUN].default is None
    assert by_key[_KEY_AUTORUN].requires == _KEY_ON
    assert _REQUIRES_MAP_FROZEN[_KEY_AUTORUN] == _KEY_ON
    assert _KEY_ON in _CATEGORY_KEYS["calidad_verificacion"]
    assert _KEY_AUTORUN in _CATEGORY_KEYS["calidad_verificacion"]
    assert _KEY_ON in _CURATED_DEFAULTS_ON
    assert _KEY_AUTORUN not in _CURATED_DEFAULTS_ON, "una flag default OFF no se cura"
    assert getattr(cfg, _KEY_ON) is True
    assert getattr(cfg, _KEY_AUTORUN) is False


def test_hook_escribe_candidato(caso):
    tid, eid, ado = caso()

    qae._post_hook(ticket_id=tid, execution_id=eid, final_status="completed",
                   agent_type="developer")

    cand = _metadata(eid)["qa_uat_candidate"]
    assert cand["status"] == "pending"
    assert cand["mode"] == "dry-run"
    assert cand["ado_id"] == ado
    assert cand["source"] == "on_execution_end"


def test_hook_ignora_no_completed(caso):
    tid, eid, _ = caso()

    qae._post_hook(ticket_id=tid, execution_id=eid, final_status="error",
                   agent_type="developer")

    assert "qa_uat_candidate" not in _metadata(eid)


def test_hook_ignora_needs_review(caso):
    tid, eid, _ = caso()

    qae._post_hook(ticket_id=tid, execution_id=eid, final_status="needs_review",
                   agent_type="developer")

    assert "qa_uat_candidate" not in _metadata(eid)


@pytest.mark.parametrize("agente", ["qa-uat", "functional", "technical", None])
def test_hook_ignora_agente_no_developer(caso, agente):
    tid, eid, _ = caso(agent_type=agente or "functional")

    qae._post_hook(ticket_id=tid, execution_id=eid, final_status="completed",
                   agent_type=agente)

    assert "qa_uat_candidate" not in _metadata(eid), "anti-recursión y scope"


def test_hook_idempotente(caso):
    tid, eid, _ = caso()

    qae._post_hook(ticket_id=tid, execution_id=eid, final_status="completed",
                   agent_type="developer")
    primero = _metadata(eid)["qa_uat_candidate"]["suggested_at"]
    qae._post_hook(ticket_id=tid, execution_id=eid, final_status="completed",
                   agent_type="developer")

    assert _metadata(eid)["qa_uat_candidate"]["suggested_at"] == primero


def test_hook_respeta_build_verdict(caso):
    tid, eid, _ = caso(metadata={"build_verdict": {"gate_ok": False, "reason": "no_sln"}})

    qae._post_hook(ticket_id=tid, execution_id=eid, final_status="completed",
                   agent_type="developer")

    assert _metadata(eid)["qa_uat_candidate"]["status"] == "blocked_by_build", \
        "no se sugiere validar algo que no compila verificado"


def test_hook_preserva_metadata_ajena(caso):
    tid, eid, _ = caso(metadata={"build_verdict": {"gate_ok": True}, "otra_key": 42})

    qae._post_hook(ticket_id=tid, execution_id=eid, final_status="completed",
                   agent_type="developer")

    md = _metadata(eid)
    assert md["otra_key"] == 42
    assert md["build_verdict"]["gate_ok"] is True
    assert md["qa_uat_candidate"]["status"] == "pending"


def test_flag_off_no_escribe(caso, monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, _KEY_ON, False, raising=False)
    tid, eid, _ = caso()

    qae._post_hook(ticket_id=tid, execution_id=eid, final_status="completed",
                   agent_type="developer")

    assert "qa_uat_candidate" not in _metadata(eid)


def test_autorun_off_por_default_no_llama(caso, monkeypatch):
    import api.qa_uat as api_qa

    llamadas: list = []
    monkeypatch.setattr(api_qa, "start_qa_uat_run",
                        lambda *a, **kw: llamadas.append(kw) or 1, raising=True)
    tid, eid, _ = caso()

    qae._post_hook(ticket_id=tid, execution_id=eid, final_status="completed",
                   agent_type="developer")

    assert llamadas == [], "el autorun es opt-in: por default no ejecuta nada"


def test_autorun_on_llama_dry_run(caso, monkeypatch):
    import api.qa_uat as api_qa
    from config import config as cfg

    monkeypatch.setattr(cfg, _KEY_AUTORUN, True, raising=False)
    llamadas: list = []
    monkeypatch.setattr(api_qa, "start_qa_uat_run",
                        lambda ado, **kw: llamadas.append((ado, kw)) or 1, raising=True)
    tid, eid, ado = caso()

    qae._post_hook(ticket_id=tid, execution_id=eid, final_status="completed",
                   agent_type="developer")

    assert len(llamadas) == 1
    assert llamadas[0][0] == ado
    assert llamadas[0][1]["mode"] == "dry-run", "el autorun NUNCA publica"


def test_autorun_no_corre_si_el_build_bloquea(caso, monkeypatch):
    import api.qa_uat as api_qa
    from config import config as cfg

    monkeypatch.setattr(cfg, _KEY_AUTORUN, True, raising=False)
    llamadas: list = []
    monkeypatch.setattr(api_qa, "start_qa_uat_run",
                        lambda *a, **kw: llamadas.append(kw) or 1, raising=True)
    tid, eid, _ = caso(metadata={"build_verdict": {"gate_ok": False}})

    qae._post_hook(ticket_id=tid, execution_id=eid, final_status="completed",
                   agent_type="developer")

    assert llamadas == []


def test_hook_nunca_lanza(monkeypatch):
    import db as db_mod

    def _boom(*a, **kw):
        raise RuntimeError("db caída")

    monkeypatch.setattr(db_mod, "session_scope", _boom, raising=True)

    qae._post_hook(ticket_id=1, execution_id=1, final_status="completed",
                   agent_type="developer")


def test_register_agrega_post_hook():
    capturados: list = []

    qae.register(capturados.append)

    assert capturados == [qae._post_hook]


# ── F4 — back-link del veredicto ─────────────────────────────────────────────

def test_backlink_actualiza_candidato(caso):
    from api.qa_uat import _update_dev_candidate

    tid, eid, _ = caso()
    qae._post_hook(ticket_id=tid, execution_id=eid, final_status="completed",
                   agent_type="developer")
    antes = _metadata(eid)["qa_uat_candidate"]

    _update_dev_candidate(tid, "PASS", 987)

    cand = _metadata(eid)["qa_uat_candidate"]
    assert cand["status"] == "validated"
    assert cand["qa_uat_execution_id"] == 987
    assert cand["ado_id"] == antes["ado_id"], "las demás keys quedan intactas"
    assert cand["suggested_at"] == antes["suggested_at"]


@pytest.mark.parametrize("verdict, esperado", [
    ("PASS", "validated"), ("FAIL", "failed"), ("MIXED", "failed"), ("BLOCKED", "blocked"),
])
def test_backlink_mapea_veredictos(caso, verdict, esperado):
    from api.qa_uat import _update_dev_candidate

    tid, eid, _ = caso()
    qae._post_hook(ticket_id=tid, execution_id=eid, final_status="completed",
                   agent_type="developer")

    _update_dev_candidate(tid, verdict, 1)

    assert _metadata(eid)["qa_uat_candidate"]["status"] == esperado


def test_backlink_sin_candidato_noop(caso):
    from api.qa_uat import _update_dev_candidate

    tid, eid, _ = caso()

    _update_dev_candidate(tid, "PASS", 1)  # no debe lanzar

    assert "qa_uat_candidate" not in _metadata(eid)


def test_backlink_verdict_desconocido_noop(caso):
    from api.qa_uat import _update_dev_candidate

    tid, eid, _ = caso()
    qae._post_hook(ticket_id=tid, execution_id=eid, final_status="completed",
                   agent_type="developer")

    _update_dev_candidate(tid, "SKIPPED", 1)

    assert _metadata(eid)["qa_uat_candidate"]["status"] == "pending"


def test_helper_start_run_existe():
    from api.qa_uat import start_qa_uat_run

    assert callable(start_qa_uat_run)


def test_registro_en_app():
    fuente = (ROOT / "app.py").read_text(encoding="utf-8")

    assert "qa_uat_enqueue.register" in fuente
