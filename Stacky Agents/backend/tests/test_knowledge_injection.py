"""Plan 170 F3 — el retorno del flywheel: inyección del bloque `evolution-lessons`
por el seam único `enrich_blocks` (contrato 133). Sin lecciones matching → identidad.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import runtime_paths
from services import context_enrichment, knowledge_store as ks


@pytest.fixture
def _env(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    from db import init_db
    init_db()
    import config
    monkeypatch.setattr(config.config, "STACKY_EVOLUTION_CENTER_ENABLED", True)
    monkeypatch.setattr(config.config, "STACKY_KNOWLEDGE_FLYWHEEL_ENABLED", True)
    monkeypatch.setattr(config.config, "STACKY_KNOWLEDGE_INJECTION_ENABLED", True)
    return tmp_path, monkeypatch


@pytest.fixture(autouse=True)
def _clean_db():
    yield
    try:
        from db import session_scope
        from models import AgentExecution, Ticket
        with session_scope() as s:
            s.query(AgentExecution).delete()
            s.query(Ticket).delete()
    except Exception:
        pass


def _seed(tmp_path, lesson_id, text, *, title=None, scope=None, created_at=None):
    ev = tmp_path / "evolution"
    ev.mkdir(parents=True, exist_ok=True)
    line = {
        "lesson_id": lesson_id, "aspect_id": "knowledge_rag", "text": text,
        "origin": "manual",
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
    }
    with (ev / "lessons.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    ks.upsert_meta(lesson_id, title=title or text[:40], scope=scope)


def _enrich(agent_type="developer", ticket_id=None):
    raw = [{"kind": "text", "id": "base", "content": "contenido base"}]
    blocks, _ = context_enrichment.enrich_blocks(
        ticket_id=ticket_id, agent_type=agent_type, raw_blocks=raw, log=None,
    )
    return blocks


def _has_block(blocks):
    return next((b for b in blocks if b.get("id") == "evolution-lessons"), None)


# 1
def test_sin_lecciones_identidad(_env):
    tmp, mp = _env
    on = _enrich()
    import config
    mp.setattr(config.config, "STACKY_KNOWLEDGE_INJECTION_ENABLED", False)
    off = _enrich()
    assert _has_block(on) is None
    assert on == off


# 2
def test_flag_injection_off_identidad(_env):
    tmp, mp = _env
    for i in range(3):
        _seed(tmp, f"l{i}", f"lección {i}")
    import config
    mp.setattr(config.config, "STACKY_KNOWLEDGE_INJECTION_ENABLED", False)
    off = _enrich()
    mp.setattr(config.config, "STACKY_KNOWLEDGE_FLYWHEEL_ENABLED", False)
    baseline = _enrich()
    assert _has_block(off) is None
    assert off == baseline


# 3
def test_inyecta_matching(_env):
    tmp, _ = _env
    _seed(tmp, "glob", "lección global", scope={"agent_types": [], "projects": []})
    _seed(tmp, "solo-qa", "lección qa", scope={"agent_types": ["qa"]})
    blocks = _enrich(agent_type="developer")
    blk = _has_block(blocks)
    assert blk is not None
    assert blk["metadata"]["lesson_ids"] == ["glob"]


# 4
def test_retired_no_se_inyecta(_env):
    tmp, _ = _env
    # meta sin línea activa (retirada)
    ks.upsert_meta("retirada", title="retirada")
    blocks = _enrich()
    assert _has_block(blocks) is None


# 5
def test_cap_duro_max_chars(_env):
    tmp, mp = _env
    for i in range(5):
        _seed(tmp, f"big{i}", "x" * 2000)
    import config
    mp.setattr(config.config, "STACKY_KNOWLEDGE_INJECT_MAX_CHARS", 3000)
    blk = _has_block(_enrich())
    assert blk is not None
    assert len(blk["content"]) <= 3000
    assert blk["metadata"]["truncated"] is True


# 6
def test_primera_leccion_gigante_se_trunca(_env):
    tmp, mp = _env
    _seed(tmp, "huge", "y" * 30000)
    import config
    mp.setattr(config.config, "STACKY_KNOWLEDGE_INJECT_MAX_CHARS", 4000)
    blk = _has_block(_enrich())
    assert blk is not None
    assert len(blk["content"]) <= 4000
    assert blk["content"].endswith("…")
    assert blk["metadata"]["truncated"] is True


# 7
def test_top_n_respeta_flag(_env):
    tmp, mp = _env
    for i in range(6):
        _seed(tmp, f"n{i}", f"lección corta {i}")
    import config
    mp.setattr(config.config, "STACKY_KNOWLEDGE_INJECT_TOP_N", 2)
    blk = _has_block(_enrich())
    assert blk is not None
    assert len(blk["metadata"]["lesson_ids"]) == 2


# 8
def test_ranking_por_query(_env):
    tmp, _ = _env
    _seed(tmp, "db", "índices de bases de datos", title="Bases de datos")
    _seed(tmp, "auth", "autenticación con sesiones y credenciales", title="Autenticación")
    from db import session_scope
    from models import Ticket
    with session_scope() as s:
        t = Ticket(ado_id=42, project="P", title="falla de autenticación",
                   description="las sesiones y credenciales fallan")
        s.add(t)
        s.flush()
        tid = t.id
    blk = _has_block(_enrich(ticket_id=tid))
    assert blk is not None
    assert blk["metadata"]["lesson_ids"][0] == "auth"


# 9
def test_contadores_se_actualizan(_env):
    tmp, _ = _env
    _seed(tmp, "u1", "lección usada")
    _enrich()
    l = ks.get_lesson("u1")
    assert l["usage_count"] == 1
    assert l["last_injected_at"] is not None


# 10
def test_prioridad_y_participa_del_budget(_env):
    assert context_enrichment._BLOCK_PRIORITY["evolution-lessons"] == 79
    assert context_enrichment._block_priority({"id": "evolution-lessons"}) == 79
    # sitúa debajo de stacky-memory (80) → podable antes que la memoria
    assert (context_enrichment._BLOCK_PRIORITY["evolution-lessons"]
            < context_enrichment._BLOCK_PRIORITY["stacky-memory"])
