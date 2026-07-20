"""Plan 170 F1 — knowledge_store: sidecar + vista compuesta + matching + dedup + LRU.

El store NUNCA escribe lessons.jsonl (READ-ONLY, G10/KPI-3): solo lessons_meta.json.
Fixture: data_dir → tmp_path (el store llama runtime_paths.data_dir() en cada op).
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

import runtime_paths
from services import knowledge_store as ks


@pytest.fixture
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    return tmp_path


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _write_lesson_line(tmp_path, lesson_id, text, *, aspect_id="knowledge_rag",
                       origin="manual", created_at=None):
    ev = tmp_path / "evolution"
    ev.mkdir(parents=True, exist_ok=True)
    line = {
        "lesson_id": lesson_id, "aspect_id": aspect_id, "text": text,
        "origin": origin,
        "created_at": created_at or _iso(datetime.now(timezone.utc)),
    }
    with (ev / "lessons.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")


# 1
def test_lessons_jsonl_ausente_da_vacio(_data_dir):
    assert ks.list_lessons() == []


# 2
def test_vista_compuesta_con_meta(_data_dir):
    _write_lesson_line(_data_dir, "prop-1", "Cuerpo de la lección uno.")
    ks.upsert_meta("prop-1", title="Título uno",
                   scope={"agent_types": ["Developer"], "projects": [], "tags": []},
                   source={"kind": "incident", "ref": "inc-9"})
    view = ks.list_lessons()
    assert len(view) == 1
    l = view[0]
    assert l["active"] is True
    assert l["title"] == "Título uno"
    assert l["scope"]["agent_types"] == ["developer"]  # casefold
    assert l["text"] == "Cuerpo de la lección uno."
    assert l["source"]["kind"] == "incident"


# 3
def test_linea_sin_meta_usa_defaults(_data_dir):
    long_first = "x" * 200
    _write_lesson_line(_data_dir, "prop-2", long_first + "\nsegunda línea")
    l = ks.get_lesson("prop-2")
    assert l is not None
    assert l["title"] == ("x" * 80)  # primera línea capada a 80
    assert l["scope"] == {"agent_types": [], "projects": [], "tags": []}
    assert l["usage_count"] == 0
    assert l["source"] == {"kind": "manual", "ref": None}


# 4
def test_retirada_va_con_include_retired(_data_dir):
    # meta sin línea activa = retirada
    ks.upsert_meta("prop-gone", title="Retirada",
                   source={"kind": "manual", "ref": None})
    assert ks.list_lessons(include_retired=False) == []
    retired = ks.list_lessons(include_retired=True)
    assert len(retired) == 1
    assert retired[0]["active"] is False
    assert retired[0]["title"] == "Retirada"


# 5
def test_lesson_matches_ejes(_data_dir):
    glob = {"agent_types": [], "projects": [], "tags": []}
    assert ks.lesson_matches(glob, agent_type="anything", project_name="p")
    assert ks.lesson_matches(glob, agent_type=None, project_name=None)
    dev = {"agent_types": ["developer"], "projects": [], "tags": []}
    assert ks.lesson_matches(dev, agent_type="developer", project_name=None)
    assert not ks.lesson_matches(dev, agent_type="qa", project_name=None)
    assert not ks.lesson_matches(dev, agent_type=None, project_name=None)
    projx = {"agent_types": [], "projects": ["x"], "tags": []}
    assert ks.lesson_matches(projx, agent_type=None, project_name="X")  # casefold
    both = {"agent_types": ["developer"], "projects": ["x"], "tags": []}
    assert ks.lesson_matches(both, agent_type="developer", project_name="X")
    assert not ks.lesson_matches(both, agent_type="developer", project_name="y")


# 6
def test_active_lessons_for_filtra(_data_dir):
    _write_lesson_line(_data_dir, "g", "global")
    _write_lesson_line(_data_dir, "d", "dev")
    _write_lesson_line(_data_dir, "q", "qa")
    ks.upsert_meta("d", title="d", scope={"agent_types": ["developer"]})
    ks.upsert_meta("q", title="q", scope={"agent_types": ["qa"]})
    out = ks.active_lessons_for("developer", None)
    ids = {l["lesson_id"] for l in out}
    assert ids == {"g", "d"}


# 7
def test_rank_lessons_tfidf_y_fallback(_data_dir):
    lessons = [
        {"lesson_id": "a", "title": "Bases de datos", "text": "índices y consultas",
         "created_at": "2026-01-01T00:00:00+00:00"},
        {"lesson_id": "b", "title": "Autenticación", "text": "tokens y sesiones",
         "created_at": "2026-06-01T00:00:00+00:00"},
    ]
    ranked = ks.rank_lessons(lessons, "problema de autenticación con sesiones", top_n=2)
    assert ranked[0]["lesson_id"] == "b"
    ranked_none = ks.rank_lessons(lessons, None, top_n=2)
    assert ranked_none[0]["lesson_id"] == "b"  # created_at DESC


# 8
def test_record_injection_incrementa(_data_dir):
    _write_lesson_line(_data_dir, "prop-x", "cuerpo")
    ks.record_injection(["prop-x"])
    ks.record_injection(["prop-x"])
    l = ks.get_lesson("prop-x")
    assert l["usage_count"] == 2
    assert l["last_injected_at"] is not None


# 9
def test_record_injection_nunca_lanza(_data_dir, monkeypatch):
    _write_lesson_line(_data_dir, "prop-y", "cuerpo")

    def _boom():
        raise OSError("disco lleno")

    monkeypatch.setattr(ks, "_meta_path", _boom)
    # No debe propagar
    ks.record_injection(["prop-y"])


# 10
def test_find_similar_titulo_exacto_y_tfidf(_data_dir):
    assert ks.find_similar("cualquier", "cosa") == []  # corpus vacío
    _write_lesson_line(_data_dir, "s1", "Nunca uses eval sobre input del usuario porque abre RCE.")
    ks.upsert_meta("s1", title="No uses eval con input externo")
    exact = ks.find_similar("no uses  eval  con   input externo", "otro cuerpo")
    assert exact and exact[0]["score"] == 1.0
    sim = ks.find_similar("Evitar eval sobre input del usuario",
                          "Nunca uses eval sobre input del usuario porque abre RCE.")
    assert any(d["score"] >= ks._DEDUP_SIMILARITY_THRESHOLD for d in sim)


# 11
def test_patch_meta_solo_title_scope(_data_dir):
    _write_lesson_line(_data_dir, "p", "cuerpo")
    ks.upsert_meta("p", title="orig")
    ks.patch_meta("p", title="nuevo")
    assert ks.get_lesson("p")["title"] == "nuevo"
    with pytest.raises(ValueError):
        ks.patch_meta("p", usage_count=99)
    with pytest.raises(KeyError):
        ks.patch_meta("no-existe", title="x")


# 12
def test_retire_suggestions_lru(_data_dir, monkeypatch):
    import config
    now = datetime.now(timezone.utc)
    data = [("A", 5, 0), ("B", 0, 1), ("C", 1, 2), ("D", 0, 3)]
    for lid, uses, days in data:
        _write_lesson_line(_data_dir, lid, f"cuerpo {lid}",
                           created_at=_iso(now - timedelta(days=days)))
        for _ in range(uses):
            ks.record_injection([lid])
    monkeypatch.setattr(config.config, "STACKY_KNOWLEDGE_MAX_LESSONS", 2)
    sugg = ks.retire_suggestions()
    assert {s["lesson_id"] for s in sugg} == {"B", "D"}
    assert all(s["reason"] == "lru_por_uso" for s in sugg)
    monkeypatch.setattr(config.config, "STACKY_KNOWLEDGE_MAX_LESSONS", 10)
    assert ks.retire_suggestions() == []


# 13
def test_harvested_ids_ignora_rechazadas_y_ajenas(_data_dir):
    from services import evolution_store as es
    a = es.create_proposal(aspect_id="knowledge_rag", title="a", rationale="r",
                           origin="agent", artifact_type="knowledge_note",
                           proposed_content="c",
                           evidence=["incident:inc-1", "harvest:llm_local"])
    b = es.create_proposal(aspect_id="knowledge_rag", title="b", rationale="r",
                           origin="agent", artifact_type="knowledge_note",
                           proposed_content="c",
                           evidence=["incident:inc-2", "harvest:plantilla"])
    es.transition(b["id"], "reject", actor="operator")
    es.create_proposal(aspect_id="knowledge_rag", title="c", rationale="r",
                       origin="mape", artifact_type="knowledge_note",
                       proposed_content="c", evidence=["incident:inc-3"])
    assert ks.harvested_incident_ids() == {"inc-1"}


# 14
def test_retire_suggestions_sin_uso_prolongado(_data_dir, monkeypatch):
    import config
    now = datetime.now(timezone.utc)
    _write_lesson_line(_data_dir, "old", "vieja sin uso",
                       created_at=_iso(now - timedelta(days=90)))
    _write_lesson_line(_data_dir, "fresh", "reciente usada",
                       created_at=_iso(now - timedelta(days=1)))
    ks.record_injection(["fresh"])
    monkeypatch.setattr(config.config, "STACKY_KNOWLEDGE_MAX_LESSONS", 10)
    sugg = ks.retire_suggestions()
    assert {s["lesson_id"] for s in sugg} == {"old"}
    assert sugg[0]["reason"] == "sin_uso_prolongado"
    # bajo cap excedido, la misma cae en LRU (precedencia regla 1)
    monkeypatch.setattr(config.config, "STACKY_KNOWLEDGE_MAX_LESSONS", 1)
    sugg2 = ks.retire_suggestions()
    old_entries = [s for s in sugg2 if s["lesson_id"] == "old"]
    assert len(old_entries) == 1
    assert old_entries[0]["reason"] == "lru_por_uso"
