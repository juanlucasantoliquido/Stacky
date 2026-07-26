"""Plan 246 F1 — barrido del repositorio (huerfanas + trigger declarado). 28 tests."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from services import pipeline_inventory as pi

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "cicd_nl" / "golden"
GOLDEN_NAMES = sorted(p.name for p in GOLDEN.glob("*.yml"))

_GITLAB_MIN = "stages:\n  - build\n  - test\n"
_NOTAS = "foo: bar\nbaz: 1\n"


@pytest.fixture()
def corpus(tmp_path: Path) -> Path:
    shutil.copytree(GOLDEN, tmp_path / "pipelines")
    (tmp_path / ".gitlab-ci.yml").write_text(_GITLAB_MIN, encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "malo.yml").write_text(_GITLAB_MIN, encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "notas.yml").write_text(_NOTAS, encoding="utf-8")
    return tmp_path


# ── scan_repo_pipelines ───────────────────────────────────────────────────────

def test_scan_encuentra_los_nueve_del_corpus_dorado(corpus: Path):
    entries, meta = pi.scan_repo_pipelines(str(corpus))
    assert meta["matched"] >= 9
    encontrados = {Path(e["yaml_path"]).name for e in entries}
    assert set(GOLDEN_NAMES) <= encontrados


def test_ningun_archivo_del_corpus_queda_sin_clasificar():
    for path in GOLDEN.glob("*.yml"):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert pi.classify_pipeline_doc(path.name, doc) is not None, path.name


def test_scan_ignora_node_modules(corpus: Path):
    entries, _meta = pi.scan_repo_pipelines(str(corpus))
    assert not any("node_modules" in e["yaml_path"] for e in entries)


def test_scan_ignora_yaml_que_no_es_pipeline(corpus: Path):
    entries, _meta = pi.scan_repo_pipelines(str(corpus))
    assert not any(e["yaml_path"].endswith("docs/notas.yml") for e in entries)


def test_scan_root_none_devuelve_vacio_y_no_lanza():
    entries, meta = pi.scan_repo_pipelines(None)
    assert entries == []
    assert meta["available"] is False
    assert meta["reason"] == "sin_workspace_activo"


def test_scan_root_inexistente_no_lanza(tmp_path: Path):
    entries, meta = pi.scan_repo_pipelines(str(tmp_path / "no-existe"))
    assert entries == []
    assert meta["available"] is False
    assert meta["reason"] == "sin_workspace_activo"


def test_scan_yaml_corrupto_no_lanza(tmp_path: Path):
    (tmp_path / "roto.yml").write_text("a: [1, 2\nb: }{\n", encoding="utf-8")
    entries, meta = pi.scan_repo_pipelines(str(tmp_path))
    assert entries == []
    assert meta["skipped_unparseable"] == 1


def test_scan_respeta_max_scan_files(corpus: Path, monkeypatch):
    monkeypatch.setattr(pi, "_MAX_SCAN_FILES", 3)
    _entries, meta = pi.scan_repo_pipelines(str(corpus))
    assert meta["truncated"] is True
    assert meta["scanned_files"] <= 3


def test_scan_salta_archivo_gigante_sin_parsear(tmp_path: Path):
    gordo = tmp_path / "gigante.yml"
    gordo.write_text("#" + ("x" * pi._MAX_YAML_BYTES), encoding="utf-8")
    entries, meta = pi.scan_repo_pipelines(str(tmp_path))
    assert meta["skipped_too_big"] == 1
    assert not any("gigante" in e["yaml_path"] for e in entries)


def test_scan_es_determinista(corpus: Path):
    a, _ = pi.scan_repo_pipelines(str(corpus))
    b, _ = pi.scan_repo_pipelines(str(corpus))
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ── classify_pipeline_doc — R1..R9 ────────────────────────────────────────────

def test_classify_r1_gitlab_por_nombre():
    assert pi.classify_pipeline_doc(".gitlab-ci.yml", {}) == "gitlab"
    assert pi.classify_pipeline_doc(".GitLab-CI.yaml", {}) == "gitlab"


def test_classify_r2_doc_no_dict():
    assert pi.classify_pipeline_doc("x.yml", ["a"]) is None
    assert pi.classify_pipeline_doc("x.yml", None) is None


def test_classify_r3_stages_lista_de_strings():
    assert pi.classify_pipeline_doc("x.yml", {"stages": ["build", "test"]}) == "gitlab"


def test_classify_r4_stages_lista_de_dicts():
    assert pi.classify_pipeline_doc("x.yml", {"stages": [{"stage": "Build"}]}) == "azure_devops"
    assert pi.classify_pipeline_doc("x.yml", {"stages": [{"template": "t.yml"}]}) == "azure_devops"


def test_classify_r5_pool_steps_jobs():
    assert pi.classify_pipeline_doc("x.yml", {"pool": {"vmImage": "ubuntu"}}) == "azure_devops"
    assert pi.classify_pipeline_doc("x.yml", {"steps": []}) == "azure_devops"
    assert pi.classify_pipeline_doc("x.yml", {"jobs": []}) == "azure_devops"


def test_classify_r6_trigger_top_level_es_ado():
    assert pi.classify_pipeline_doc("x.yml", {"trigger": "none"}) == "azure_devops"
    assert pi.classify_pipeline_doc("x.yml", {"trigger": ["main"]}) == "azure_devops"
    assert pi.classify_pipeline_doc(
        "x.yml", {"trigger": {"branches": {"include": ["main"]}}}
    ) == "azure_devops"


def test_classify_r7_workflow_include():
    assert pi.classify_pipeline_doc("x.yml", {"workflow": {"rules": []}}) == "gitlab"
    assert pi.classify_pipeline_doc("x.yml", {"include": [{"local": "a.yml"}]}) == "gitlab"


def test_classify_r8_job_con_script():
    assert pi.classify_pipeline_doc("x.yml", {"build": {"script": ["make"]}}) == "gitlab"


def test_classify_r9_ninguna_regla():
    assert pi.classify_pipeline_doc("x.yml", {"foo": "bar"}) is None


# ── extract_trigger ───────────────────────────────────────────────────────────

def test_trigger_ado_ausente_es_default():
    assert pi.extract_trigger({}, "azure_devops")["kind"] == "default"


def test_trigger_ado_none():
    assert pi.extract_trigger({"trigger": "none"}, "azure_devops")["kind"] == "none"
    assert pi.extract_trigger({"trigger": None}, "azure_devops")["kind"] == "none"


def test_trigger_ado_lista_de_ramas():
    t = pi.extract_trigger({"trigger": ["main", "dev"]}, "azure_devops")
    assert t["kind"] == "ci"
    assert t["branches"] == ["main", "dev"]


def test_trigger_ado_dict_con_include_y_paths():
    t = pi.extract_trigger(
        {"trigger": {"branches": {"include": ["main"]}, "paths": {"include": ["src"]}}},
        "azure_devops",
    )
    assert t["branches"] == ["main"]
    assert t["has_paths"] is True


def test_trigger_ado_schedules_y_pr():
    t = pi.extract_trigger({"schedules": [{"cron": "0 0 * * *"}], "pr": "none"}, "azure_devops")
    assert t["has_schedule"] is True
    assert t["has_pr"] is False
    t2 = pi.extract_trigger({"pr": {"branches": {"include": ["main"]}}}, "azure_devops")
    assert t2["has_pr"] is True


def test_trigger_gitlab_merge_request_event():
    doc = {"workflow": {"rules": [{"if": '$CI_PIPELINE_SOURCE == "merge_request_event"'}]}}
    assert pi.extract_trigger(doc, "gitlab")["has_pr"] is True


def test_trigger_gitlab_declara_sus_limitaciones():
    doc = {"build": {"script": ["make"], "only": ["main"]}, "schedules": [{"cron": "x"}]}
    t = pi.extract_trigger(doc, "gitlab")
    assert t["branches"] == []
    assert t["has_schedule"] is False


def test_trigger_shape_siempre_completo():
    casos = [
        ({}, "azure_devops"),
        ({"trigger": "none"}, "azure_devops"),
        ({"trigger": ["main"]}, "azure_devops"),
        ({"trigger": {"branches": {"include": ["main"]}}}, "azure_devops"),
        ({"trigger": 42}, "azure_devops"),
        ({"workflow": {"rules": []}}, "gitlab"),
        ({"foo": "bar"}, "gitlab"),
        ("no-dict", "gitlab"),
    ]
    claves = {"kind", "branches", "has_paths", "has_schedule", "has_pr", "source"}
    for doc, provider in casos:
        assert set(pi.extract_trigger(doc, provider)) == claves


def test_extract_trigger_no_devuelve_texto_crudo():
    for path in GOLDEN.glob("*.yml"):
        raw = path.read_text(encoding="utf-8")
        doc = yaml.safe_load(raw)
        provider = pi.classify_pipeline_doc(path.name, doc)
        trig = pi.extract_trigger(doc, provider or "azure_devops")
        planos = [v for v in trig.values() if isinstance(v, str)]
        planos += [b for b in trig["branches"] if isinstance(b, str)]
        for value in planos:
            assert "\n" not in value
            assert value not in (raw,)
            assert len(value) < 200
