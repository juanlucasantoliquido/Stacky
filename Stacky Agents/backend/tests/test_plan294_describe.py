"""tests/test_plan294_describe.py — Plan 294 F2 (+ F10).

`get_pipeline_yaml` cierra el bug vivo GAP-6 (el perfilador por `pipeline_id`
devolvia 501 SIEMPRE porque importaba una funcion que nunca existio) y
`describe_pipeline` le da al inventario la ficha en castellano que el perfilador
ya sabe generar, SIN gastar un token.

R10 es el riel duro de este archivo: `describe_pipeline` AGREGA claves; las 12 de
`make_entry` (contrato congelado que consumen los planes 247..252) siguen con el
mismo nombre y el mismo valor.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

_YAML_OK = """\
trigger:
  branches:
    include:
      - main
pool:
  vmImage: windows-latest
steps:
  - task: DotNetCoreCLI@2
    inputs:
      command: build
  - task: DotNetCoreCLI@2
    inputs:
      command: test
  - task: PublishBuildArtifacts@1
    inputs:
      ArtifactName: publish
"""

_YAML_DEPLOY = """\
stages:
  - stage: Deploy
    jobs:
      - deployment: DeployProd
        environment: produccion
        strategy:
          runOnce:
            deploy:
              steps:
                - script: echo desplegando
"""


def _entry(**over):
    from services.pipeline_inventory import make_entry

    base = dict(
        provider="azure_devops",
        name="ci",
        yaml_path="azure-pipelines.yml",
        default_branch="main",
        definition_id="147",
        category="registrada+en_repo",
        category_reason="",
        trigger={"kind": "ci", "branches": ["main"]},
        found_in=("ado_definitions",),
        hints=[],
    )
    base.update(over)
    return make_entry(**base)


# ─────────────────────────────────────────────── get_pipeline_yaml (GAP-6)


def test_get_pipeline_yaml_se_puede_importar():
    """Cierra el caso 6 de test_plan294_baseline.py."""
    from services.pipeline_inventory import get_pipeline_yaml

    assert callable(get_pipeline_yaml)


def test_get_pipeline_yaml_lee_del_workspace(tmp_path, monkeypatch):
    import services.pipeline_inventory as inv

    (tmp_path / "azure-pipelines.yml").write_text(_YAML_OK, encoding="utf-8")
    monkeypatch.setattr(
        "runtime_paths._active_workspace_root", lambda: tmp_path, raising=True
    )

    texto, rel = inv.get_pipeline_yaml("azure_devops::azure-pipelines.yml")
    assert "DotNetCoreCLI" in texto
    assert rel == "azure-pipelines.yml"


def test_key_registrada_sin_archivo_lanza_keyerror(tmp_path, monkeypatch):
    import services.pipeline_inventory as inv

    monkeypatch.setattr(
        "runtime_paths._active_workspace_root", lambda: tmp_path, raising=True
    )
    with pytest.raises(KeyError):
        inv.get_pipeline_yaml("azure_devops::#def147")


def test_traversal_lanza_keyerror_y_no_lee(tmp_path, monkeypatch):
    """El archivo de afuera EXISTE: si el guard no estuviera, la funcion lo leeria."""
    import services.pipeline_inventory as inv

    afuera = tmp_path.parent / "secreto_294.txt"
    afuera.write_text("no me leas", encoding="utf-8")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    monkeypatch.setattr(
        "runtime_paths._active_workspace_root", lambda: workspace, raising=True
    )

    with pytest.raises(KeyError):
        inv.get_pipeline_yaml("azure_devops::../secreto_294.txt")


def test_archivo_mas_grande_que_el_cap_lanza_keyerror(tmp_path, monkeypatch):
    import services.pipeline_inventory as inv

    grande = tmp_path / "azure-pipelines.yml"
    grande.write_text("#" * (inv._MAX_YAML_BYTES + 10), encoding="utf-8")
    monkeypatch.setattr(
        "runtime_paths._active_workspace_root", lambda: tmp_path, raising=True
    )

    with pytest.raises(KeyError):
        inv.get_pipeline_yaml("azure_devops::azure-pipelines.yml")


# ─────────────────────────────────────────────────────── describe_pipeline


def test_describe_con_yaml_valido_trae_ficha_de_plantilla():
    from services.pipeline_inventory import describe_pipeline

    out = describe_pipeline(_entry(), _YAML_OK)
    assert out["purpose"].strip(), "la frase en castellano vino vacia"
    assert out["purpose_source"] == "plantilla"
    assert len(out["purpose"]) <= 200
    assert out["stages_es"], "no se derivaron etapas"


def test_describe_sin_yaml_degrada_sin_lanzar():
    from services.pipeline_inventory import describe_pipeline

    out = describe_pipeline(_entry(), None)
    assert out["purpose_source"] == "sin_datos"
    assert out["purpose"] == ""
    assert out["stages_es"] == []
    assert out["artifacts_es"] == []
    assert out["environments_es"] == []


def test_describe_con_yaml_roto_no_lanza():
    from services.pipeline_inventory import describe_pipeline

    out = describe_pipeline(_entry(), "a: [\n")
    assert out["purpose_source"] == "sin_datos"


def test_r10_las_doce_claves_de_make_entry_siguen_iguales():
    from services.pipeline_inventory import describe_pipeline

    entry = _entry()
    out = describe_pipeline(entry, _YAML_OK)
    doce = (
        "key", "provider", "name", "yaml_path", "default_branch", "definition_id",
        "category", "category_reason", "last_run", "trigger", "found_in", "hints",
    )
    assert len(entry) == 12, "make_entry dejo de tener 12 claves"
    for clave in doce:
        assert clave in out, f"describe_pipeline perdio la clave {clave}"
        assert out[clave] == entry[clave], f"describe_pipeline cambio el valor de {clave}"


def test_describe_no_hace_red(monkeypatch):
    import socket

    class _Prohibido(socket.socket):
        def __init__(self, *a, **k):  # noqa: D107
            raise AssertionError("describe_pipeline intento abrir un socket")

    monkeypatch.setattr(socket, "socket", _Prohibido)

    from services.pipeline_inventory import describe_pipeline

    out = describe_pipeline(_entry(), _YAML_OK)
    assert out["purpose_source"] == "plantilla"


def test_frase_de_trigger_tolera_un_kind_desconocido():
    """R12 — el vocabulario del proveedor es ABIERTO. Un lookup con [] lanzaria
    KeyError y, como el llamador atrapa todo, un proyecto sano apareceria sin
    ficha. La tabla se consulta SIEMPRE con .get()."""
    from services.pipeline_inventory import _WHEN_ES, _frase_de_trigger

    frase = _frase_de_trigger({"kind": "scheduled", "branches": []})
    assert frase == _WHEN_ES["unknown"]
    assert _frase_de_trigger({}) == _WHEN_ES["unknown"]


# ═══════════════════════════════════════════════════════════════════════════
# Plan 294 F10 — el inventario se conecta: parametro `describe` y ficha honesta
# de despliegue. R10 en las DOS direcciones: sin el parametro nada cambia, y
# CON el parametro tampoco se pierde nada.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def app():
    from app import create_app

    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def _inventario_falso(monkeypatch):
    import services.pipeline_inventory as inv

    inv.clear_cache()

    def _fake(project=None, *, refresh=False, describe=False):
        entradas = [_entry()]
        if describe:
            entradas = [inv.describe_pipeline(e, _YAML_OK) for e in entradas]
        return {
            "ok": True, "generated_at": "", "cached": False, "cache_age_sec": 0,
            "project": project or "", "counts": {}, "sources": [],
            "pipelines": entradas,
        }

    monkeypatch.setattr(inv, "build_inventory", _fake)
    import api.pipeline_inventory as api_inv

    monkeypatch.setattr(api_inv, "build_inventory", _fake)
    yield
    inv.clear_cache()


@pytest.fixture(autouse=True)
def _inventario_on(monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_INVENTORY_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_PROFILER_ENABLED", True, raising=False)
    yield


def test_f10_sin_describe_la_respuesta_es_la_de_hoy(app, _inventario_falso):
    resp = app.test_client().get("/api/pipeline-inventory/list")
    assert resp.status_code == 200
    entrada = resp.get_json()["pipelines"][0]
    assert len(entrada) == 12, sorted(entrada)
    assert "purpose" not in entrada


def test_f10_con_describe_las_entradas_traen_la_ficha(app, _inventario_falso):
    resp = app.test_client().get("/api/pipeline-inventory/list?describe=1")
    assert resp.status_code == 200
    entrada = resp.get_json()["pipelines"][0]
    assert entrada["purpose"].strip()
    assert entrada["when_es"].strip()


def test_f10_el_cache_no_se_cruza(tmp_path, monkeypatch):
    """Sin `describe` en la clave del cache, un pedido SIN ficha envenena al
    pedido CON ficha durante los 5 minutos del TTL."""
    import services.pipeline_inventory as inv

    inv.clear_cache()
    monkeypatch.setattr(inv, "scan_repo_pipelines", lambda root: ([], {"available": True, "matched": 0, "scanned_files": 0}))

    sin = inv.build_inventory("proyecto-294")
    con = inv.build_inventory("proyecto-294", describe=True)
    assert sin["project"] == con["project"]
    claves = set(inv._CACHE)
    assert len(claves) == 2, f"la clave del cache no distingue `describe`: {claves}"
    inv.clear_cache()


def test_f10_la_ficha_de_despliegue_es_honesta_en_los_tres_casos():
    """El peor error posible del plan es afirmar 'no despliega' sobre una
    pipeline que despliega a produccion. Lista VACIA con ficha de plantilla es
    una AFIRMACION; sin datos es IGNORANCIA. No son lo mismo."""
    from services.pipeline_inventory import describe_pipeline

    despliega = describe_pipeline(_entry(), _YAML_DEPLOY)
    assert despliega["environments_es"], despliega
    assert despliega["purpose_source"] == "plantilla"

    solo_build = describe_pipeline(_entry(), _YAML_OK)
    assert solo_build["environments_es"] == []
    assert solo_build["purpose_source"] == "plantilla"

    sin_datos = describe_pipeline(_entry(), None)
    assert sin_datos["environments_es"] == []
    assert sin_datos["purpose_source"] == "sin_datos"

    entry = _entry()
    assert len(entry) == 12
    assert len(despliega) == 12 + 6, sorted(set(despliega) - set(entry))


def test_f10_r10_con_describe_no_se_pierde_ninguna_de_las_doce(app, _inventario_falso):
    c = app.test_client()
    sin = c.get("/api/pipeline-inventory/list").get_json()["pipelines"][0]
    con = c.get("/api/pipeline-inventory/list?describe=1").get_json()["pipelines"][0]
    for clave, valor in sin.items():
        assert clave in con, f"?describe=1 perdio {clave}"
        assert con[clave] == valor, f"?describe=1 cambio el valor de {clave}"


def test_f10_el_perfilador_apagado_degrada_la_ficha_no_la_lista(app, _inventario_falso, monkeypatch):
    """El inventario esta gateado por SU flag; la ficha depende de OTRA. Que
    falte la segunda degrada la ficha, nunca la lista. Nunca 500, nunca 404."""
    import config as cfg
    import services.pipeline_inventory as inv

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_PROFILER_ENABLED", False, raising=False)
    inv.clear_cache()

    resp = app.test_client().get("/api/pipeline-inventory/list?describe=1")
    assert resp.status_code == 200
    entrada = resp.get_json()["pipelines"][0]
    assert entrada["purpose_source"] == "sin_datos"
    for clave in ("key", "provider", "name", "yaml_path", "default_branch",
                  "definition_id", "category", "category_reason", "last_run",
                  "trigger", "found_in", "hints"):
        assert clave in entrada
