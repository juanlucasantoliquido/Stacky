"""Plan 60 F4 — Tests de services/ado_edit_learning.py.

Verifica: lección determinista por revisión humana, idempotencia (ledger),
no-PII (sin autor en corpus), degradación limpia si plan 56 ausente.
"""
from __future__ import annotations

import pytest

# ── Fixtures de revisiones ADO (shape real de /updates) ──────────────────────

_BASELINE_HTML = (
    "<h1>EP-1 Portal</h1>"
    "<h2>RF-1 — Autenticación</h2>"
    "<p>El usuario debe poder iniciar sesión.</p>"
)
_EDITED_HTML = (
    "<h1>EP-1 Portal</h1>"
    "<h2>RF-1 — Autenticación</h2>"
    "<p>El usuario debe poder iniciar sesión de forma segura con MFA obligatorio "
    "para cumplir requisitos de seguridad corporativa.</p>"
)
# Solo whitespace adicional — no material
_WHITESPACE_HTML = (
    "<h1>EP-1 Portal</h1>"
    "<h2>RF-1 — Autenticación</h2>"
    "<p>El  usuario  debe  poder  iniciar  sesión.</p>"
)

_REV_STACKY = {
    "rev": 1,
    "revisedBy": {"uniqueName": "stacky@empresa.com"},
    "fields": {"System.Description": {"oldValue": "", "newValue": _BASELINE_HTML}},
}
_REV_HUMAN = {
    "rev": 2,
    "revisedBy": {"uniqueName": "operador@empresa.com"},
    "fields": {"System.Description": {"oldValue": _BASELINE_HTML, "newValue": _EDITED_HTML}},
}
_REV_WHITESPACE = {
    "rev": 2,
    "revisedBy": {"uniqueName": "operador@empresa.com"},
    "fields": {"System.Description": {"oldValue": _BASELINE_HTML, "newValue": _WHITESPACE_HTML}},
}


class FakeAdo:
    def __init__(self, revisions=None, raise_on_fetch=False):
        self._revisions = revisions or []
        self._raise = raise_on_fetch

    def fetch_work_item_updates(self, ado_id, top=50):
        if self._raise:
            raise RuntimeError("ADO unavailable")
        return self._revisions


@pytest.fixture()
def mem_ledger(monkeypatch, tmp_path):
    """Ledger con DB en tmpdir para aislamiento por test."""
    import services.ado_edit_ledger as lm
    db_path = str(tmp_path / "test_ledger.db")
    monkeypatch.setattr(lm, "_get_db_path", lambda: db_path)
    monkeypatch.setattr(lm, "_get_jsonl_path", lambda: tmp_path / "ledger.jsonl")
    lm._create_table_if_needed()
    return lm


@pytest.fixture()
def captured_save(monkeypatch):
    """Captura llamadas a memory_store.save_observation."""
    calls = []
    import services.memory_store as ms
    monkeypatch.setattr(ms, "save_observation", lambda **kw: (calls.append(kw), "fid")[1])
    return calls


@pytest.fixture(autouse=True)
def captured_golden(monkeypatch):
    """Captura save_golden (plan 56) y EVITA escribir goldens reales en el repo.

    Autouse: cualquier test cuyo HTML editado tenga heading RF dispararía
    derive_positive_golden+save_golden tras el fix del bridge; sin este stub
    la suite dejaría de ser hermética (escribiría harness/goldens/*.json).
    """
    calls = []
    import harness.regression_goldens as rg
    monkeypatch.setattr(rg, "save_golden", lambda g: calls.append(g))
    return calls


# ── Tests F4 ─────────────────────────────────────────────────────────────────

def test_no_revisions_returns_unavailable(mem_ledger, captured_save):
    """fetch_work_item_updates => [] => learned=False, no lección."""
    from services.ado_edit_learning import learn_from_work_item
    result = learn_from_work_item(
        ado_id=100, baseline_html=_BASELINE_HTML, baseline_rev=1,
        baseline_author="stacky@empresa.com", run_id="r1", project_name="P",
        ado_client=FakeAdo(revisions=[]),
        service_identities=set(),
    )
    assert result.learned is False
    assert result.reason in {"ado_unavailable", "no_human_edit"}
    assert not captured_save


def test_human_revision_writes_lesson(mem_ledger, captured_save):
    """Revisión humana material => learned=True, lesson_written=True, tipo/tags correctos."""
    from services.ado_edit_learning import learn_from_work_item
    result = learn_from_work_item(
        ado_id=101, baseline_html=_BASELINE_HTML, baseline_rev=1,
        baseline_author="stacky@empresa.com", run_id="r1", project_name="P",
        ado_client=FakeAdo(revisions=[_REV_STACKY, _REV_HUMAN]),
        service_identities=set(),
    )
    assert result.learned is True
    assert result.lesson_written is True
    assert result.rev == 2
    assert result.reason == "ok"
    assert len(captured_save) == 1
    kw = captured_save[0]
    assert kw["type"] == "operator_note"
    assert "approval_condition" in kw["tags"]
    assert "ado_human_edit" in kw["tags"]
    assert mem_ledger.already_learned(101, 2)


def test_second_call_is_idempotent(mem_ledger, captured_save):
    """Segunda llamada con misma rev ya en ledger => learned=False."""
    from services.ado_edit_learning import learn_from_work_item
    kwargs = dict(
        ado_id=102, baseline_html=_BASELINE_HTML, baseline_rev=1,
        baseline_author="stacky@empresa.com", run_id="r1", project_name="P",
        ado_client=FakeAdo(revisions=[_REV_STACKY, _REV_HUMAN]),
        service_identities=set(),
    )
    learn_from_work_item(**kwargs)
    captured_save.clear()
    result2 = learn_from_work_item(**kwargs)
    assert result2.learned is False
    assert result2.reason in {"already_learned", "no_human_edit"}
    assert not captured_save


def test_whitespace_only_not_material(mem_ledger, captured_save):
    """Edición solo-whitespace => not_material, no lección, ledger no marcado."""
    from services.ado_edit_learning import learn_from_work_item
    result = learn_from_work_item(
        ado_id=103, baseline_html=_BASELINE_HTML, baseline_rev=1,
        baseline_author="stacky@empresa.com", run_id="r1", project_name="P",
        ado_client=FakeAdo(revisions=[_REV_STACKY, _REV_WHITESPACE]),
        service_identities=set(),
    )
    assert result.learned is False
    assert result.reason == "not_material"
    assert not captured_save
    assert not mem_ledger.already_learned(103, 2)


def test_golden_not_available_golden_false(mem_ledger, captured_save, monkeypatch):
    """Plan 56 ausente => golden_written=False, lesson_written=True (degradación limpia)."""
    import services.ado_edit_learning as lm
    monkeypatch.setattr(lm, "_golden_available", lambda: False)
    result = lm.learn_from_work_item(
        ado_id=104, baseline_html=_BASELINE_HTML, baseline_rev=1,
        baseline_author="stacky@empresa.com", run_id="r1", project_name="P",
        ado_client=FakeAdo(revisions=[_REV_STACKY, _REV_HUMAN]),
        service_identities=set(),
    )
    assert result.lesson_written is True
    assert result.golden_written is False


def test_golden_available_writes_positive_golden(mem_ledger, captured_save, captured_golden):
    """Plan 56 PRESENTE + edición humana con heading RF => golden_written=True.

    Cierra el bridge muerto: el golden positivo se guarda con LAS MISMAS keys que
    lee el gate de autopublish (api/tickets.py:6103-6107 BusinessAgent/Epic), si no
    quedaría huérfano. La versión humana corregida pasa a ser baseline de calidad.
    """
    import services.ado_edit_learning as lm
    # Precondición firsthand: el plan 56 ya está implementado (API viva), no el placeholder.
    assert lm._golden_available() is True
    result = lm.learn_from_work_item(
        ado_id=106, baseline_html=_BASELINE_HTML, baseline_rev=1,
        baseline_author="stacky@empresa.com", run_id="r1", project_name="P",
        ado_client=FakeAdo(revisions=[_REV_STACKY, _REV_HUMAN]),
        service_identities=set(),
    )
    assert result.learned is True
    assert result.lesson_written is True
    assert result.golden_written is True
    assert len(captured_golden) == 1
    g = captured_golden[0]
    assert g.kind == "positive"
    assert g.project == "P"
    assert g.agent_type == "BusinessAgent"
    assert g.work_item_type == "Epic"


def test_edit_to_lesson_content_deterministic():
    """edit_to_lesson_content produce texto determinista con bullets added/removed."""
    from harness.ado_edit_diff import diff_edit
    from services.ado_edit_learning import edit_to_lesson_content
    delta = diff_edit(_BASELINE_HTML, _EDITED_HTML)
    content = edit_to_lesson_content(delta, ado_id=200)
    assert "WI 200" in content
    assert "Incorporá" in content


def test_no_pii_in_lesson_content(mem_ledger, captured_save):
    """C4 — autor ('operador@empresa.com') NO aparece en content ni en kwargs de save_observation."""
    from services.ado_edit_learning import learn_from_work_item
    learn_from_work_item(
        ado_id=105, baseline_html=_BASELINE_HTML, baseline_rev=1,
        baseline_author="stacky@empresa.com", run_id="r1", project_name="P",
        ado_client=FakeAdo(revisions=[_REV_STACKY, _REV_HUMAN]),
        service_identities=set(),
    )
    assert len(captured_save) == 1
    kw = captured_save[0]
    content = kw.get("content", "")
    assert "operador@empresa.com" not in content
    assert kw.get("author_email") is None
