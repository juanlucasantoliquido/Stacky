"""Plan 246 F0 — nucleo determinista de reconciliacion (PURO).

26 tests (17 de la v1 + 9 de la v2). Sin red, sin disco, sin LLM.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from services import pipeline_inventory as pi


# ── normalize_yaml_path ───────────────────────────────────────────────────────

def test_normalize_preserva_punto_inicial_de_gitlab_ci():
    """TRAMPA: lstrip('./') borraria el punto y partiria la identidad de GitLab."""
    assert pi.normalize_yaml_path(".gitlab-ci.yml") == ".gitlab-ci.yml"
    assert pi.normalize_yaml_path("./.gitlab-ci.yml") == ".gitlab-ci.yml"


def test_normalize_backslash_y_prefijos():
    assert pi.normalize_yaml_path("..\\pipelines\\CI.yml") == "../pipelines/ci.yml"
    assert pi.normalize_yaml_path("./pipelines/ci.yml") == "pipelines/ci.yml"
    assert pi.normalize_yaml_path("././pipelines/ci.yml") == "pipelines/ci.yml"
    assert pi.normalize_yaml_path("/pipelines/ci.yml") == "pipelines/ci.yml"
    assert pi.normalize_yaml_path("pipelines/CI.yml") == "pipelines/ci.yml"


def test_normalize_none_y_vacio():
    assert pi.normalize_yaml_path(None) == ""
    assert pi.normalize_yaml_path("") == ""


# ── identity_key ──────────────────────────────────────────────────────────────

def test_identity_key_con_y_sin_yaml():
    assert pi.identity_key("azure_devops", "pipelines/ci.yml") == "azure_devops::pipelines/ci.yml"
    assert pi.identity_key("azure_devops", None, "7") == "azure_devops::#def7"
    assert pi.identity_key("azure_devops", None, None) == "azure_devops::#desconocida"


def test_identity_key_es_estable_entre_llamadas():
    vals = {pi.identity_key("gitlab", "./Pipelines/CI.yml", "9") for _ in range(100)}
    assert len(vals) == 1


# ── make_entry ────────────────────────────────────────────────────────────────

def test_make_entry_tiene_las_12_claves():
    entry = pi.make_entry(
        provider="azure_devops",
        name="CI",
        yaml_path="pipelines/ci.yml",
        default_branch=None,
        definition_id=None,
        category=pi.CATEGORY_REGISTERED_WITH_FILE,
    )
    esperadas = {
        "key", "provider", "name", "yaml_path", "default_branch", "definition_id",
        "category", "category_reason", "last_run", "trigger", "found_in", "hints",
    }
    assert set(entry) == esperadas
    assert entry["hints"] == []
    assert entry["last_run"]["status"] == "unknown"
    assert entry["last_run"]["run_id"] is None
    assert entry["trigger"]["kind"] == "unknown"


# ── reconcile ─────────────────────────────────────────────────────────────────

def _reg(**kw):
    base = {
        "provider": "azure_devops",
        "name": "CI",
        "yaml_path": "pipelines/ci.yml",
        "default_branch": "main",
        "definition_id": "7",
    }
    base.update(kw)
    return base


def _file(**kw):
    base = {
        "provider": "azure_devops",
        "name": "ci",
        "yaml_path": "pipelines/ci.yml",
        "trigger": {"kind": "ci", "branches": ["main"], "source": "yaml"},
    }
    base.update(kw)
    return base


def test_reconcile_ambas_fuentes_da_registrada_en_repo():
    out = pi.reconcile([_reg()], [_file()])
    assert len(out) == 1
    assert out[0]["category"] == "registrada+en_repo"
    assert out[0]["found_in"] == ("ado_definitions", "repo_scan")


def test_reconcile_prioriza_proveedor_para_nombre_y_disco_para_trigger():
    out = pi.reconcile([_reg(name="Nombre del proveedor")], [_file(name="nombre del disco")])
    assert out[0]["name"] == "Nombre del proveedor"
    assert out[0]["trigger"]["kind"] == "ci"
    assert out[0]["trigger"]["branches"] == ["main"]


def test_reconcile_solo_registrada_sin_archivo():
    out = pi.reconcile([_reg()], [])
    assert out[0]["category"] == "registrada_sin_archivo"
    assert out[0]["category_reason"] == "archivo_ausente_en_repo"


def test_reconcile_definicion_sin_yaml_declarado():
    out = pi.reconcile([_reg(yaml_path=None)], [])
    assert out[0]["category"] == "registrada_sin_archivo"
    assert out[0]["category_reason"] == "sin_yaml_declarado"


def test_reconcile_huerfana():
    out = pi.reconcile([], [_file()])
    assert out[0]["category"] == "en_repo_sin_registrar"
    assert out[0]["category_reason"] == "huerfana"
    assert out[0]["last_run"]["status"] == "never_ran"
    assert out[0]["last_run"]["status_detail"] == "no_registrada"


def test_reconcile_es_determinista():
    regs = [_reg(), _reg(yaml_path="pipelines/b.yml", definition_id="8", name="B")]
    files = [_file(), _file(yaml_path="pipelines/c.yml", name="C")]
    a = pi.reconcile(regs, files)
    b = pi.reconcile(list(reversed(regs)), list(reversed(files)))
    assert json.dumps(a, sort_keys=True, default=list) == json.dumps(b, sort_keys=True, default=list)


def test_reconcile_listas_vacias():
    assert pi.reconcile([], []) == []
    c = pi.counts([])
    assert c["total"] == 0
    for cat in pi.CATEGORIES:
        assert c[cat] == 0


def test_sort_key_pone_las_rotas_primero():
    out = pi.reconcile(
        [_reg(), _reg(yaml_path="pipelines/sana.yml", definition_id="8", name="Sana")],
        [_file(yaml_path="pipelines/sana.yml", name="Sana"), _file(yaml_path="pipelines/huerfana.yml", name="Huerfana")],
    )
    cats = [e["category"] for e in out]
    assert cats == ["registrada_sin_archivo", "en_repo_sin_registrar", "registrada+en_repo"]


def test_counts_suma_total():
    out = pi.reconcile([_reg()], [_file(yaml_path="pipelines/otra.yml", name="Otra")])
    c = pi.counts(out)
    assert c["total"] == len(out)
    assert sum(c[cat] for cat in pi.CATEGORIES) == c["total"]


def test_source_unavailable_tiene_el_shape_de_capability_unavailable():
    from services.tracker_provider import CapabilityUnavailable

    src = pi.source_unavailable(
        "ado_definitions",
        capability="list_pipeline_definitions",
        provider="azure_devops",
        reason="sin PAT",
        workaround="Configura el PAT",
    )
    payload = CapabilityUnavailable(
        "list_pipeline_definitions", "azure_devops", reason="x", workaround="y"
    ).to_payload()
    for k in ("available", "capability", "provider", "reason", "workaround"):
        assert k in src and k in payload
    for k in ("capability", "provider", "reason", "workaround"):
        assert isinstance(src[k], str)
    assert src["available"] is False
    assert src["count"] == 0


def test_f0_no_importa_red_ni_disco():
    """El modulo no depende de red a nivel de modulo. difflib SI esta permitido."""
    ruta = Path(pi.__file__)
    tree = ast.parse(ruta.read_text(encoding="utf-8"))
    top_level_imports: set[str] = set()
    for node in tree.body:  # SOLO nivel de modulo, no dentro de funciones
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level_imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            top_level_imports.add(mod)
            if (node.module or "") == "os":
                for alias in node.names:
                    assert alias.name != "walk", "prohibido `from os import walk`"
    prohibidos = {"urllib", "requests", "ado_client", "gitlab_client"}
    assert not (top_level_imports & prohibidos), top_level_imports
    assert "ado_client" not in pi.__dict__
    assert "gitlab_client" not in pi.__dict__
    assert "difflib" in top_level_imports


def test_reconcile_scan_no_confiable_no_marca_rota():
    regs = [
        _reg(yaml_path="pipelines/a.yml", definition_id="1", name="A"),
        _reg(yaml_path="pipelines/b.yml", definition_id="2", name="B"),
        _reg(yaml_path="pipelines/c.yml", definition_id="3", name="C"),
    ]
    out = pi.reconcile(regs, [], scan_reliable=False)
    assert len(out) == 3
    assert all(e["category"] == "registrada_estado_desconocido" for e in out)
    assert all(e["category_reason"] == "barrido_no_confiable" for e in out)
    assert not any(e["category"] == "registrada_sin_archivo" for e in out)


def test_reconcile_scan_confiable_si_marca_rota():
    regs = [
        _reg(yaml_path="pipelines/a.yml", definition_id="1", name="A"),
        _reg(yaml_path="pipelines/b.yml", definition_id="2", name="B"),
        _reg(yaml_path="pipelines/c.yml", definition_id="3", name="C"),
    ]
    out = pi.reconcile(regs, [], scan_reliable=True)
    assert all(e["category"] == "registrada_sin_archivo" for e in out)


def test_reconcile_segunda_pasada_une_cross_provider():
    out = pi.reconcile(
        [_reg(provider="azure_devops", yaml_path="pipelines/ci.yml")],
        [_file(provider="gitlab", yaml_path="pipelines/ci.yml")],
    )
    assert len(out) == 1
    assert out[0]["category"] == "registrada+en_repo"
    assert out[0]["category_reason"] == "match_por_ruta_cross_provider"


def test_reconcile_segunda_pasada_no_une_rutas_vacias():
    out = pi.reconcile(
        [_reg(yaml_path=None, definition_id="7")],
        [_file(provider="gitlab", yaml_path="")],
    )
    assert len(out) == 2
    cats = sorted(e["category"] for e in out)
    assert cats == ["en_repo_sin_registrar", "registrada_sin_archivo"]


def test_counts_incluye_las_cuatro_categorias():
    c = pi.counts([])
    assert len(c) == 5
    assert set(c) == {"total", *pi.CATEGORIES}
    assert all(v == 0 for v in c.values())


def test_sort_key_pone_desconocido_ultimo():
    desconocida = pi.make_entry(
        provider="azure_devops", name="X", yaml_path="a.yml", default_branch=None,
        definition_id=None, category=pi.CATEGORY_UNKNOWN_FILE_STATE,
    )
    sana = pi.make_entry(
        provider="azure_devops", name="X", yaml_path="a.yml", default_branch=None,
        definition_id=None, category=pi.CATEGORY_REGISTERED_WITH_FILE,
    )
    assert pi.sort_key(desconocida)[0] == 3
    assert pi.sort_key(sana)[0] == 2
    assert pi.sort_key(sana) < pi.sort_key(desconocida)


def test_nearest_repo_paths_encuentra_la_parecida():
    out = pi.nearest_repo_paths(
        "pipelines/ci-online.yml", ["pipelines/ci_online.yml", "docs/x.yml"]
    )
    assert out and out[0] == "pipelines/ci_online.yml"


@pytest.mark.parametrize("target", [None, ""])
def test_nearest_repo_paths_bordes(target):
    assert pi.nearest_repo_paths(target, ["a.yml"]) == []
    assert pi.nearest_repo_paths("pipelines/ci.yml", []) == []
    muchos = [f"pipelines/ci{i}.yml" for i in range(10)]
    assert len(pi.nearest_repo_paths("pipelines/ci.yml", muchos, limit=2)) <= 2


def test_nearest_repo_paths_es_determinista():
    cands = ["pipelines/ci_online.yml", "pipelines/ci-batch.yml", "docs/x.yml"]
    vals = {tuple(pi.nearest_repo_paths("pipelines/ci-online.yml", cands)) for _ in range(100)}
    assert len(vals) == 1
