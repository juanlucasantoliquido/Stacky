"""Plan 81 — Golden negativo desde ediciones ADO (F0..F4).

Suite única del plan:
- F0: derivador puro removed_snippets -> goldens negativos.
- F0b: matching tag-agnóstico en evaluate_regression (rama negativa).
- F1: wiring en learn_from_work_item + campo LearnResult.
- F2: registro de flag editable por UI y categorización.
- F3: E2E del loop (learn -> load_goldens -> evaluate_epic_gate).
"""
from __future__ import annotations

import pytest


BASELINE_HTML = (
    "<h1>EP-81</h1>"
    "<h2>RF-01 Flujo</h2>"
    "<p>El sistema registra la operación de inicio de proceso. "
    "El proceso Mul2Bane transfiere los archivos a la carpeta temporal para auditoria continua.</p>"
)

EDITED_HTML_REMOVED = (
    "<h1>EP-81</h1>"
    "<h2>RF-01 Flujo</h2>"
    "<p>El sistema registra la operación de inicio de proceso.</p>"
)

REMOVED_PHRASE = "El proceso Mul2Bane transfiere los archivos a la carpeta temporal para auditoria continua"


class FakeAdo:
    def __init__(self, revisions=None, raise_on_fetch=False):
        self._revisions = revisions or []
        self._raise = raise_on_fetch

    def fetch_work_item_updates(self, ado_id, top=50):
        if self._raise:
            raise RuntimeError("ADO unavailable")
        return self._revisions


def _revisions_for_edit(edited_html: str):
    rev_stacky = {
        "rev": 1,
        "revisedBy": {"uniqueName": "stacky@empresa.com"},
        "fields": {"System.Description": {"oldValue": "", "newValue": BASELINE_HTML}},
    }
    rev_human = {
        "rev": 2,
        "revisedBy": {"uniqueName": "operador@empresa.com"},
        "fields": {"System.Description": {"oldValue": BASELINE_HTML, "newValue": edited_html}},
    }
    return [rev_stacky, rev_human]


@pytest.fixture()
def mem_ledger(monkeypatch, tmp_path):
    import services.ado_edit_ledger as lm

    db_path = str(tmp_path / "plan81_ledger.db")
    monkeypatch.setattr(lm, "_get_db_path", lambda: db_path)
    monkeypatch.setattr(lm, "_get_jsonl_path", lambda: tmp_path / "plan81_ledger.jsonl")
    lm._create_table_if_needed()
    return lm


@pytest.fixture(autouse=True)
def stub_save_observation(monkeypatch):
    import services.memory_store as ms

    monkeypatch.setattr(ms, "save_observation", lambda **kw: "obs-id")


def _use_tmp_goldens(monkeypatch, tmp_path):
    import harness.regression_goldens as rg

    monkeypatch.setattr(rg, "_GOLDENS_DIR", tmp_path / "goldens")


# ---------------------------------------------------------------------------
# F0 — derive_negative_goldens_from_removed
# ---------------------------------------------------------------------------

def test_f0_removed_snippet_becomes_negative_golden():
    from harness.regression_goldens import derive_negative_goldens_from_removed, _normalize

    out = derive_negative_goldens_from_removed(
        removed_snippets=[REMOVED_PHRASE],
        edited_text="texto distinto sin la frase borrada",
        project="P81",
        agent_type="BusinessAgent",
        work_item_type="Epic",
    )

    assert len(out) == 1
    g = out[0]
    assert g.kind == "negative"
    assert g.check == "absent_substring"
    assert g.value == _normalize(REMOVED_PHRASE)
    assert g.project == "P81"
    assert g.agent_type == "BusinessAgent"
    assert g.work_item_type == "Epic"


def test_f0_short_snippet_is_skipped():
    from harness.regression_goldens import derive_negative_goldens_from_removed

    out = derive_negative_goldens_from_removed(
        removed_snippets=["el proceso"],
        edited_text="texto nuevo",
        project="P81",
        agent_type="BusinessAgent",
        work_item_type="Epic",
    )
    assert out == []


def test_f0_snippet_still_present_in_edited_is_skipped():
    from harness.regression_goldens import derive_negative_goldens_from_removed

    snippet = "La operación mantiene trazabilidad completa para auditoria"
    out = derive_negative_goldens_from_removed(
        removed_snippets=[snippet],
        edited_text=f"Se reordenó formato, pero sigue: {snippet}",
        project="P81",
        agent_type="BusinessAgent",
        work_item_type="Epic",
    )
    assert out == []


def test_f0_dedup_within_same_edit():
    from harness.regression_goldens import derive_negative_goldens_from_removed

    out = derive_negative_goldens_from_removed(
        removed_snippets=[
            "La plataforma asegura envío confiable de documentos para análisis posterior",
            "   la plataforma   asegura ENVÍO confiable de documentos para análisis posterior   ",
        ],
        edited_text="contenido distinto",
        project="P81",
        agent_type="BusinessAgent",
        work_item_type="Epic",
    )
    assert len(out) == 1


def test_f0_cap_max_five():
    from harness.regression_goldens import derive_negative_goldens_from_removed

    snippets = [f"Frase removida muy larga número {i} para superar el umbral mínimo de longitud" for i in range(8)]
    out = derive_negative_goldens_from_removed(
        removed_snippets=snippets,
        edited_text="texto editado sin frases removidas",
        project="P81",
        agent_type="BusinessAgent",
        work_item_type="Epic",
    )
    assert len(out) == 5
    assert [g.value for g in out] == [
        "frase removida muy larga número 0 para superar el umbral mínimo de longitud",
        "frase removida muy larga número 1 para superar el umbral mínimo de longitud",
        "frase removida muy larga número 2 para superar el umbral mínimo de longitud",
        "frase removida muy larga número 3 para superar el umbral mínimo de longitud",
        "frase removida muy larga número 4 para superar el umbral mínimo de longitud",
    ]


def test_f0_empty_and_none_inputs():
    from harness.regression_goldens import derive_negative_goldens_from_removed

    assert derive_negative_goldens_from_removed(
        removed_snippets=[],
        edited_text="",
        project="P81",
        agent_type="BusinessAgent",
        work_item_type="Epic",
    ) == []

    assert derive_negative_goldens_from_removed(
        removed_snippets=None,
        edited_text="",
        project="P81",
        agent_type="BusinessAgent",
        work_item_type="Epic",
    ) == []


def test_f0_pure_and_deterministic():
    from harness.regression_goldens import derive_negative_goldens_from_removed

    kwargs = dict(
        removed_snippets=[REMOVED_PHRASE],
        edited_text="texto sin frase removida",
        project="P81",
        agent_type="BusinessAgent",
        work_item_type="Epic",
    )
    a = derive_negative_goldens_from_removed(**kwargs)
    b = derive_negative_goldens_from_removed(**kwargs)
    assert a == b


# ---------------------------------------------------------------------------
# F0b — evaluate_regression negativo tag-agnóstico
# ---------------------------------------------------------------------------

def test_f0b_negative_matches_through_inline_tags():
    from harness.regression_goldens import Golden, evaluate_regression, _normalize

    value = _normalize("El proceso Mul2Bane transfiere los archivos")
    goldens = [
        Golden("negative", "absent_substring", value, "P81", "BusinessAgent", "Epic")
    ]
    html = "<p>El proceso <strong>Mul2Bane</strong> transfiere los archivos a carpeta temporal</p>"

    defects = evaluate_regression(clean_html=html, goldens=goldens, process_catalog=[])
    assert defects == [f"regression_negative:{value}"]


def test_f0b_negative_plain_text_still_matches():
    from harness.regression_goldens import Golden, evaluate_regression, _normalize

    value = _normalize("El proceso Mul2Bane transfiere los archivos")
    goldens = [
        Golden("negative", "absent_substring", value, "P81", "BusinessAgent", "Epic")
    ]
    html = "<p>El proceso Mul2Bane transfiere los archivos a carpeta temporal</p>"

    defects = evaluate_regression(clean_html=html, goldens=goldens, process_catalog=[])
    assert defects == [f"regression_negative:{value}"]


def test_f0b_positive_branch_unchanged():
    from harness.regression_goldens import Golden, evaluate_regression, _normalize

    expected_heading = _normalize("RF-01 Descripción")
    golden = Golden("positive", "present_heading", expected_heading, "P81", "BusinessAgent", "Epic")

    html_ok = "<h1>Épica</h1><h2>RF-01 Descripción</h2><p>Contenido.</p>"
    assert evaluate_regression(clean_html=html_ok, goldens=[golden], process_catalog=[]) == []

    html_missing = "<h1>Épica</h1><p>Sin heading RF</p>"
    assert evaluate_regression(clean_html=html_missing, goldens=[golden], process_catalog=[]) == [
        f"regression_positive_missing:{expected_heading}"
    ]


# ---------------------------------------------------------------------------
# F1 — wiring learn_from_work_item + LearnResult
# ---------------------------------------------------------------------------

def test_f1_flag_on_persists_negative_golden(monkeypatch, tmp_path, mem_ledger):
    from services.ado_edit_learning import learn_from_work_item
    from harness.regression_goldens import load_goldens, _normalize

    monkeypatch.setenv("STACKY_NEGATIVE_GOLDEN_FROM_EDITS_ENABLED", "true")
    _use_tmp_goldens(monkeypatch, tmp_path)

    res = learn_from_work_item(
        ado_id=8101,
        baseline_html=BASELINE_HTML,
        baseline_rev=1,
        baseline_author="stacky@empresa.com",
        run_id="run-81-1",
        project_name="P81",
        ado_client=FakeAdo(revisions=_revisions_for_edit(EDITED_HTML_REMOVED)),
        service_identities=set(),
    )

    assert res.learned is True
    assert res.reason == "ok"
    assert res.negative_goldens_written == 1

    goldens = load_goldens(project="P81", agent_type="BusinessAgent", work_item_type="Epic")
    negatives = [g for g in goldens if g.kind == "negative"]
    assert len(negatives) == 1
    assert negatives[0].value == _normalize(REMOVED_PHRASE)


def test_f1_flag_off_is_noop(monkeypatch, tmp_path, mem_ledger):
    from services.ado_edit_learning import learn_from_work_item
    from harness.regression_goldens import load_goldens

    monkeypatch.delenv("STACKY_NEGATIVE_GOLDEN_FROM_EDITS_ENABLED", raising=False)
    _use_tmp_goldens(monkeypatch, tmp_path)

    res = learn_from_work_item(
        ado_id=8102,
        baseline_html=BASELINE_HTML,
        baseline_rev=1,
        baseline_author="stacky@empresa.com",
        run_id="run-81-2",
        project_name="P81",
        ado_client=FakeAdo(revisions=_revisions_for_edit(EDITED_HTML_REMOVED)),
        service_identities=set(),
    )

    assert res.learned is True
    assert res.lesson_written is True
    assert res.golden_written is True
    assert res.negative_goldens_written == 0

    goldens = load_goldens(project="P81", agent_type="BusinessAgent", work_item_type="Epic")
    assert [g for g in goldens if g.kind == "negative"] == []


def test_f1_save_golden_failure_is_non_fatal(monkeypatch, tmp_path, mem_ledger):
    import harness.regression_goldens as rg
    from services.ado_edit_learning import learn_from_work_item

    monkeypatch.setenv("STACKY_NEGATIVE_GOLDEN_FROM_EDITS_ENABLED", "true")
    _use_tmp_goldens(monkeypatch, tmp_path)

    def _boom(_g):
        raise RuntimeError("boom")

    monkeypatch.setattr(rg, "save_golden", _boom)

    res = learn_from_work_item(
        ado_id=8103,
        baseline_html=BASELINE_HTML,
        baseline_rev=1,
        baseline_author="stacky@empresa.com",
        run_id="run-81-3",
        project_name="P81",
        ado_client=FakeAdo(revisions=_revisions_for_edit(EDITED_HTML_REMOVED)),
        service_identities=set(),
    )

    assert res.reason == "ok"
    assert res.learned is True
    assert res.negative_goldens_written == 0


def test_f1_learnresult_backward_compatible():
    from services.ado_edit_learning import LearnResult

    r = LearnResult(
        learned=False,
        lesson_written=False,
        golden_written=False,
        rev=None,
        reason="x",
    )
    assert r.negative_goldens_written == 0


# ---------------------------------------------------------------------------
# F2 — flag registry/UI wiring
# ---------------------------------------------------------------------------

def test_f2_flag_registered_ui_editable():
    from services.harness_flags import FLAG_REGISTRY

    spec = next(s for s in FLAG_REGISTRY if s.key == "STACKY_NEGATIVE_GOLDEN_FROM_EDITS_ENABLED")
    assert spec.type == "bool"
    assert spec.env_only is False


def test_f2_flag_categorized_aprendizaje():
    from services.harness_flags import _CATEGORY_KEYS

    assert "STACKY_NEGATIVE_GOLDEN_FROM_EDITS_ENABLED" in _CATEGORY_KEYS["aprendizaje"]


def test_f2_flag_has_no_explicit_default():
    from services.harness_flags import FLAG_REGISTRY

    spec = next(s for s in FLAG_REGISTRY if s.key == "STACKY_NEGATIVE_GOLDEN_FROM_EDITS_ENABLED")
    assert spec.default is None


# ---------------------------------------------------------------------------
# F3 — E2E loop learn -> gate regression
# ---------------------------------------------------------------------------

def _learn_and_load_goldens(monkeypatch, tmp_path, mem_ledger, *, ado_id: int, flag_on: bool):
    from services.ado_edit_learning import learn_from_work_item
    from harness.regression_goldens import load_goldens

    if flag_on:
        monkeypatch.setenv("STACKY_NEGATIVE_GOLDEN_FROM_EDITS_ENABLED", "true")
    else:
        monkeypatch.delenv("STACKY_NEGATIVE_GOLDEN_FROM_EDITS_ENABLED", raising=False)

    _use_tmp_goldens(monkeypatch, tmp_path)

    result = learn_from_work_item(
        ado_id=ado_id,
        baseline_html=BASELINE_HTML,
        baseline_rev=1,
        baseline_author="stacky@empresa.com",
        run_id=f"run-{ado_id}",
        project_name="P81",
        ado_client=FakeAdo(revisions=_revisions_for_edit(EDITED_HTML_REMOVED)),
        service_identities=set(),
    )
    goldens = load_goldens(project="P81", agent_type="BusinessAgent", work_item_type="Epic")
    return result, goldens


def test_f3_e2e_deleted_text_blocks_recurrence(monkeypatch, tmp_path, mem_ledger):
    from harness.epic_gate import evaluate_epic_gate

    _, goldens = _learn_and_load_goldens(monkeypatch, tmp_path, mem_ledger, ado_id=8201, flag_on=True)
    negatives = [g for g in goldens if g.kind == "negative"]
    assert len(negatives) == 1

    future_html = (
        "<h1>EP-81</h1><h2>RF-01 Flujo</h2>"
        "<p>El proceso Mul2Bane transfiere los archivos a la carpeta temporal para auditoria continua.</p>"
    )
    verdict = evaluate_epic_gate(
        clean_html=future_html,
        structural_warnings=[],
        process_catalog=None,
        catalog_blocking_enabled=False,
        looks_like_epic_fn=lambda _h: True,
        regression_goldens=goldens,
        regression_blocking_enabled=False,
    )

    assert verdict.regression_defects == [f"regression_negative:{negatives[0].value}"]
    assert verdict.blocking is False


def test_f3_e2e_blocking_mode_blocks(monkeypatch, tmp_path, mem_ledger):
    from harness.epic_gate import evaluate_epic_gate, GateDecision

    _, goldens = _learn_and_load_goldens(monkeypatch, tmp_path, mem_ledger, ado_id=8202, flag_on=True)
    negative = next(g for g in goldens if g.kind == "negative")

    future_html = (
        "<h1>EP-81</h1><h2>RF-01 Flujo</h2>"
        "<p>El proceso Mul2Bane transfiere los archivos a la carpeta temporal para auditoria continua.</p>"
    )
    verdict = evaluate_epic_gate(
        clean_html=future_html,
        structural_warnings=[],
        process_catalog=None,
        catalog_blocking_enabled=False,
        looks_like_epic_fn=lambda _h: True,
        regression_goldens=goldens,
        regression_blocking_enabled=True,
    )

    assert verdict.regression_defects == [f"regression_negative:{negative.value}"]
    assert verdict.blocking is True
    assert verdict.decision == GateDecision.NEEDS_REVIEW


def test_f3_e2e_clean_epic_passes(monkeypatch, tmp_path, mem_ledger):
    from harness.epic_gate import evaluate_epic_gate, GateDecision

    _, goldens = _learn_and_load_goldens(monkeypatch, tmp_path, mem_ledger, ado_id=8203, flag_on=True)

    clean_html = "<h1>EP-81</h1><h2>RF-01 Flujo</h2><p>Flujo limpio sin frase removida.</p>"
    verdict = evaluate_epic_gate(
        clean_html=clean_html,
        structural_warnings=[],
        process_catalog=None,
        catalog_blocking_enabled=False,
        looks_like_epic_fn=lambda _h: True,
        regression_goldens=goldens,
        regression_blocking_enabled=False,
    )

    assert verdict.regression_defects == []
    assert verdict.decision == GateDecision.PASS


def test_f3_flags_off_byte_identical(monkeypatch, tmp_path, mem_ledger):
    result, goldens = _learn_and_load_goldens(monkeypatch, tmp_path, mem_ledger, ado_id=8204, flag_on=False)

    assert (result.learned, result.lesson_written, result.golden_written, result.reason) == (
        True,
        True,
        True,
        "ok",
    )
    assert result.negative_goldens_written == 0
    assert [g for g in goldens if g.kind == "negative"] == []


def test_f3_e2e_tagged_reappearance_detected(monkeypatch, tmp_path, mem_ledger):
    from harness.epic_gate import evaluate_epic_gate

    _, goldens = _learn_and_load_goldens(monkeypatch, tmp_path, mem_ledger, ado_id=8205, flag_on=True)
    negative = next(g for g in goldens if g.kind == "negative")

    tagged_html = (
        "<h1>EP-81</h1><h2>RF-01 Flujo</h2>"
        "<p>El proceso <strong>Mul2Bane</strong> transfiere los archivos a la carpeta temporal para auditoria continua.</p>"
    )
    verdict = evaluate_epic_gate(
        clean_html=tagged_html,
        structural_warnings=[],
        process_catalog=None,
        catalog_blocking_enabled=False,
        looks_like_epic_fn=lambda _h: True,
        regression_goldens=goldens,
        regression_blocking_enabled=False,
    )

    assert verdict.regression_defects == [f"regression_negative:{negative.value}"]
