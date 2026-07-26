"""Plan 248 F2 — las 4 reglas OPT. 14 tests (8 positivo/negativo + 6 numerados)."""
from __future__ import annotations

from pathlib import Path

from services.cicd_audit_core import AUDIT_RULES, MODE_AUDIT, MODE_NL_STRICT, job_key
from services.pipeline_recommendations import check_recommendations

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "cicd_nl" / "golden"


def _codes(yaml_text: str, provider: str = "ado", mode: str = MODE_AUDIT) -> list:
    findings, _notes = check_recommendations(yaml_text, provider=provider, mode=mode)
    return [f.code for f in findings]


def _repro(code: str) -> str:
    return AUDIT_RULES[code].repro[1]


def _golden(nombre: str) -> str:
    return (GOLDEN / nombre).read_text(encoding="utf-8")


# ── OPT001 ────────────────────────────────────────────────────────────────────

def test_opt001_positivo_pr_con_restore_sin_cache():
    assert "OPT001" in _codes(_repro("OPT001"))


def test_opt001_negativo_con_cache_no_dispara():
    con_cache = _repro("OPT001") + "- task: Cache@2\n  inputs:\n    key: 'x'\n"
    assert "OPT001" not in _codes(con_cache)


# ── OPT002 ────────────────────────────────────────────────────────────────────

def test_opt002_positivo_build_y_test_en_el_mismo_job():
    assert "OPT002" in _codes(_repro("OPT002"))


def test_opt002_negativo_con_no_build():
    assert "OPT002" not in _codes(
        _repro("OPT002").replace("'--configuration Release'", "'--no-build'"))


# ── OPT003 ────────────────────────────────────────────────────────────────────

def test_opt003_positivo_selfhosted_sin_timeout():
    assert "OPT003" in _codes(_repro("OPT003"))


def test_opt003_negativo_con_timeout_en_el_stage():
    con_timeout = _repro("OPT003").replace("- job: Deploy\n", "- job: Deploy\n  timeoutInMinutes: 30\n")
    assert "OPT003" not in _codes(con_timeout)


# ── OPT004 ────────────────────────────────────────────────────────────────────

def test_opt004_positivo_checkout_explicito_sin_fetchdepth():
    assert "OPT004" in _codes(_repro("OPT004"))


def test_opt004_negativo_con_fetchdepth_1():
    assert "OPT004" not in _codes("steps:\n- checkout: self\n  fetchDepth: 1\n")


# ── Recuentos exactos contra el corpus real ──────────────────────────────────

def test_opt001_dispara_en_los_3_pipelines_de_pr():
    esperados = {"ci-batch.yml", "ci-dacpac.yml", "pr-validation-online.yml"}
    con_hit = set()
    for path in sorted(GOLDEN.glob("*.yml")):
        if "OPT001" in _codes(path.read_text(encoding="utf-8")):
            con_hit.add(path.name)
    assert con_hit == esperados


def test_opt002_dispara_en_pr_validation_online():
    """C2 — con el rsplit crudo de la v1 este test da 0. Es el gate del bloqueante."""
    findings, _ = check_recommendations(_golden("pr-validation-online.yml"), provider="ado")
    assert len([f for f in findings if f.code == "OPT002"]) == 1


def test_opt002_no_dispara_en_agendaweb_ci():
    """Control negativo. El segundo assert hace que ese 0 SIGNIFIQUE algo (C2)."""
    import yaml
    from services.cicd_audit_core import iter_steps

    crudo = _golden("agendaweb-ci.yml")
    findings, _ = check_recommendations(crudo, provider="ado")
    assert not [f for f in findings if f.code == "OPT002"]

    doc = yaml.safe_load(crudo)
    ctxs = iter_steps(doc)
    assert {job_key(c.location) for c in ctxs} == {"(root)"}
    builds = [c for c in ctxs if str(c.step.get("task") or "") == "VSBuild@1"]
    assert builds and job_key(builds[0].location) == "(root)"


def test_opt003_dispara_solo_en_cd_deploy_test():
    findings, _ = check_recommendations(_golden("cd-deploy-test.yml"), provider="ado")
    opt003 = [f for f in findings if f.code == "OPT003"]
    assert [f.line for f in opt003] == [123, 162]

    _f, notes = check_recommendations(
        _golden("bootstrap-server-environment.yml"), provider="ado")
    assert len([n for n in notes if n.startswith("OPT003")]) == 1

    for path in sorted(GOLDEN.glob("*.yml")):
        if path.name == "cd-deploy-test.yml":
            continue
        assert "OPT003" not in _codes(path.read_text(encoding="utf-8")), path.name


def test_opt004_ignora_el_checkout_implicito():
    assert "OPT004" not in _codes(_golden("ci-cd-online.yml"))
    findings, _ = check_recommendations(_golden("cd-deploy-test.yml"), provider="ado")
    assert len([f for f in findings if f.code == "OPT004"]) == 2


def test_recommendations_no_evalua_en_nl_strict():
    for path in sorted(GOLDEN.glob("*.yml")):
        assert check_recommendations(
            path.read_text(encoding="utf-8"), provider="ado", mode=MODE_NL_STRICT) == ((), ())


def test_recuentos_exactos_del_corpus():
    """OPT001 = 3, OPT002 = 3, OPT003 = 2, OPT004 = 3. Un numero distinto = regla movida."""
    totales = {}
    for path in sorted(GOLDEN.glob("*.yml")):
        for code in _codes(path.read_text(encoding="utf-8")):
            totales[code] = totales.get(code, 0) + 1
    assert totales == {"OPT001": 3, "OPT002": 3, "OPT003": 2, "OPT004": 3}
