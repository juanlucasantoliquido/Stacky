"""Plan 246 F2 + F3 — fuentes ADO / GitLab y ensamblado con degradacion honesta.

37 tests (16 de F2 + 21 de F3). Sin red real: clientes falsos que CUENTAN llamadas
sobre `_request` (contar la capa de afuera es como la v1 se dio un falso verde).
"""
from __future__ import annotations

import json

import pytest

import services.ado_client as ado_client_module
from services import ado_pipeline_definitions as apd
from services import pipeline_inventory as pi
from services.ado_ci_provider import AdoCIProvider
from services.gitlab_ci_provider import GitLabCIProvider
from services.tracker_provider import TrackerApiError, TrackerConfigError


@pytest.fixture(autouse=True)
def _limpiar_cache():
    pi.clear_cache()
    yield
    pi.clear_cache()


# ═══════════════════════════ F2 — fuente Azure DevOps ═══════════════════════════

def make_fake_ado(
    *,
    definitions: list[dict] | None = None,
    builds: list[dict] | None = None,
    raise_definitions: bool = False,
    raise_builds: bool = False,
    detail_yaml: str | None = "pipelines/hidratada.yml",
):
    calls: list[str] = []

    class FakeAdoClient:
        def __init__(self, project=None):
            self._base_proj = "https://dev.azure.com/org/proj"

        def _request(self, method, url, body=None):
            calls.append(url)
            if "/build/builds" in url:
                if raise_builds:
                    raise RuntimeError("builds caido")
                return {"value": list(builds or [])}
            if "/build/definitions/" in url:
                return {"process": {"yamlFilename": detail_yaml}}
            if "/build/definitions" in url:
                if raise_definitions:
                    raise RuntimeError("definitions caido")
                return {"value": list(definitions or [])}
            raise AssertionError(f"URL inesperada: {url}")

    FakeAdoClient.calls = calls
    return FakeAdoClient


def _defs_con_process(n: int) -> list[dict]:
    return [
        {
            "id": i,
            "name": f"Pipeline {i}",
            "process": {"yamlFilename": f"pipelines/ci{i}.yml"},
            "repository": {"defaultBranch": "refs/heads/main"},
            "queueStatus": "enabled",
        }
        for i in range(1, n + 1)
    ]


def _defs_sin_process(n: int) -> list[dict]:
    return [
        {"id": i, "name": f"Pipeline {i}", "repository": {"defaultBranch": "refs/heads/dev"}}
        for i in range(1, n + 1)
    ]


def test_list_definitions_una_sola_llamada_cuando_hay_process(monkeypatch):
    fake = make_fake_ado(definitions=_defs_con_process(5))
    monkeypatch.setattr(ado_client_module, "AdoClient", fake)
    out, meta = apd.list_definitions(None)
    assert len(out) == 5
    assert meta["calls"] == 1
    assert meta["hydrated"] == 0


def test_list_definitions_hidrata_como_mucho_diez(monkeypatch):
    fake = make_fake_ado(definitions=_defs_sin_process(25))
    monkeypatch.setattr(ado_client_module, "AdoClient", fake)
    _out, meta = apd.list_definitions(None)
    assert meta["calls"] == 11
    assert meta["hydrated"] == 10
    assert meta["truncated_hydration"] is True


def test_list_definitions_respeta_max_definitions(monkeypatch):
    fake = make_fake_ado(definitions=_defs_con_process(80))
    monkeypatch.setattr(ado_client_module, "AdoClient", fake)
    out, meta = apd.list_definitions(None)
    assert len(out) == 50
    assert meta["capped"] is True


def test_list_definitions_strip_refs_heads(monkeypatch):
    fake = make_fake_ado(definitions=_defs_con_process(1))
    monkeypatch.setattr(ado_client_module, "AdoClient", fake)
    out, _meta = apd.list_definitions(None)
    assert out[0]["default_branch"] == "main"
    assert apd._strip_refs_heads(None) == ""
    assert apd._strip_refs_heads("main") == "main"


def test_list_definitions_excepcion_no_lanza(monkeypatch):
    fake = make_fake_ado(raise_definitions=True)
    monkeypatch.setattr(ado_client_module, "AdoClient", fake)
    out, meta = apd.list_definitions(None)
    assert out == []
    assert meta["available"] is False
    assert meta["reason"]


def test_list_definitions_body_vacio(monkeypatch):
    fake = make_fake_ado(definitions=[])
    monkeypatch.setattr(ado_client_module, "AdoClient", fake)
    out, meta = apd.list_definitions(None)
    assert out == []
    assert meta["available"] is True
    assert meta["calls"] == 1


def _builds(*specs) -> list[dict]:
    out = []
    for def_id, build_id, status, result in specs:
        out.append(
            {
                "id": build_id,
                "status": status,
                "result": result,
                "definition": {"id": def_id},
                "finishTime": "2026-07-26T10:00:00Z",
                "_links": {"web": {"href": f"https://ado/build/{build_id}"}},
            }
        )
    return out


def test_provider_lista_y_ultima_corrida_en_dos_llamadas(monkeypatch):
    fake = make_fake_ado(
        definitions=_defs_con_process(5),
        builds=_builds((1, 100, "completed", "succeeded")),
    )
    monkeypatch.setattr(ado_client_module, "AdoClient", fake)
    out, _meta = AdoCIProvider(project=None).list_pipeline_definitions()
    assert len(out) == 5
    assert len(fake.calls) == 2


def test_provider_agrupa_builds_por_definicion(monkeypatch):
    fake = make_fake_ado(
        definitions=_defs_con_process(9),
        builds=_builds(
            (7, 700, "completed", "succeeded"),
            (7, 699, "completed", "failed"),
            (7, 698, "completed", "failed"),
            (9, 900, "completed", "failed"),
        ),
    )
    monkeypatch.setattr(ado_client_module, "AdoClient", fake)
    out, _meta = AdoCIProvider(project=None).list_pipeline_definitions()
    por_id = {e["definition_id"]: e for e in out}
    assert por_id["7"]["last_run"]["run_id"] == "700"
    assert por_id["7"]["last_run"]["status"] == "success"
    assert por_id["9"]["last_run"]["run_id"] == "900"
    assert por_id["9"]["last_run"]["status"] == "failed"


@pytest.mark.parametrize(
    "build,esperado",
    [
        ({"status": "completed", "result": "succeeded"}, ("success", "success")),
        ({"status": "completed", "result": "failed"}, ("failed", "failed")),
        ({"status": "completed", "result": "canceled"}, ("unknown", "canceled")),
        ({"status": "inProgress", "result": ""}, ("unknown", "running")),
    ],
)
def test_provider_mapea_status_con_map_status(build, esperado):
    from services.ado_ci_provider import _map_status

    assert pi.map_run_status(_map_status(build)) == esperado


@pytest.mark.parametrize(
    "raw", ["waiting_for_resource", "preparing", "scheduled", "", None]
)
def test_map_run_status_no_lanza_con_vocabulario_desconocido(raw):
    status, detail = pi.map_run_status(raw)
    assert status == "unknown"
    assert isinstance(detail, str) and detail


def test_provider_definicion_sin_builds_es_never_ran(monkeypatch):
    fake = make_fake_ado(definitions=_defs_con_process(2), builds=[])
    monkeypatch.setattr(ado_client_module, "AdoClient", fake)
    out, _meta = AdoCIProvider(project=None).list_pipeline_definitions()
    assert all(e["last_run"]["status"] == "never_ran" for e in out)
    assert all(e["last_run"]["status_detail"] == "sin_corridas" for e in out)


def test_run_id_es_str_o_none(monkeypatch):
    fake = make_fake_ado(
        definitions=_defs_con_process(2),
        builds=_builds((1, 4711, "completed", "succeeded")),
    )
    monkeypatch.setattr(ado_client_module, "AdoClient", fake)
    out, _meta = AdoCIProvider(project=None).list_pipeline_definitions()
    por_id = {e["definition_id"]: e for e in out}
    assert isinstance(por_id["1"]["last_run"]["run_id"], str)
    assert por_id["2"]["last_run"]["run_id"] is None


def test_meta_arrastra_las_claves_de_truncacion(monkeypatch):
    fake = make_fake_ado(definitions=_defs_con_process(80), builds=[])
    monkeypatch.setattr(ado_client_module, "AdoClient", fake)
    _out, meta = AdoCIProvider(project=None).list_pipeline_definitions()
    assert meta["capped"] is True

    fake2 = make_fake_ado(definitions=_defs_sin_process(25), builds=[])
    monkeypatch.setattr(ado_client_module, "AdoClient", fake2)
    _out2, meta2 = AdoCIProvider(project=None).list_pipeline_definitions()
    assert meta2["truncated_hydration"] is True
    assert meta2["hydrated"] == 10


def test_provider_batch_caido_no_hace_n_llamadas(monkeypatch):
    fake = make_fake_ado(definitions=_defs_con_process(5), raise_builds=True)
    monkeypatch.setattr(ado_client_module, "AdoClient", fake)
    out, _meta = AdoCIProvider(project=None).list_pipeline_definitions()
    assert len(fake.calls) == 2
    assert all(e["last_run"]["status"] == "unknown" for e in out)
    assert all(e["last_run"]["status_detail"] == "batch_no_soportado" for e in out)


def test_provider_nunca_lanza(monkeypatch):
    fake = make_fake_ado(raise_definitions=True, raise_builds=True)
    monkeypatch.setattr(ado_client_module, "AdoClient", fake)
    out, meta = AdoCIProvider(project=None).list_pipeline_definitions()
    assert out == []
    assert meta["available"] is False


def test_ci_port_methods_sigue_congelado():
    from services import ci_provider

    assert ci_provider.CI_PORT_METHODS == (
        "infer_item_pipeline",
        "monitor_pipeline",
        "trigger_pipeline",
    )


# ═══════════════════════════ F3 — fuente GitLab ═════════════════════════════════

def make_fake_gitlab(
    *,
    project_body: dict | None = None,
    pipelines: list | None = None,
    raise_project: bool = False,
    raise_pipelines: bool = False,
):
    class FakeGitLabClient:
        def __init__(self):
            self.calls: list[tuple] = []

        def _project_path(self):
            return "grp%2Fproj"

        def _request(self, method, path, *, params=None, json_body=None, files=None, _retry=0):
            self.calls.append((method, path, params))
            if path.endswith("/pipelines"):
                if raise_pipelines:
                    raise TrackerApiError(status=500, kind="gl", message="pipelines caido")
                return (list(pipelines or []), {})
            if raise_project:
                raise TrackerApiError(status=404, kind="gl", message="proyecto caido")
            return (dict(project_body or {}), {})

    return FakeGitLabClient()


class _FakeDelegate:
    """Delegate minimo: expone `_client` y un fetch_pipelines que es un CENTINELA.

    Si el inventario vuelve a usar el listado paginado, este metodo hace fallar el test
    con el motivo escrito (pagina hasta 40 GET).
    """

    def __init__(self, client):
        self._client = client

    def fetch_pipelines(self, ref=None):
        raise AssertionError("prohibido: pagina hasta 40")


def _gitlab_provider(client) -> GitLabCIProvider:
    prov = GitLabCIProvider.__new__(GitLabCIProvider)
    prov._project = None
    prov._delegate = _FakeDelegate(client)
    return prov


def test_gitlab_usa_ci_config_path_cuando_viene():
    client = make_fake_gitlab(project_body={"ci_config_path": "ci/gl.yml"})
    out, meta = _gitlab_provider(client).list_pipeline_definitions()
    assert meta["available"] is True
    assert out[0]["yaml_path"] == "ci/gl.yml"
    assert out[0]["yaml_path_source"] == "proyecto"


def test_gitlab_cae_a_convencion_si_falta_la_key():
    client = make_fake_gitlab(project_body={})
    out, _meta = _gitlab_provider(client).list_pipeline_definitions()
    assert out[0]["yaml_path"] == ".gitlab-ci.yml"
    assert out[0]["yaml_path_source"] == "convencion"


def test_gitlab_cae_a_convencion_si_la_llamada_lanza():
    client = make_fake_gitlab(raise_project=True)
    out, _meta = _gitlab_provider(client).list_pipeline_definitions()
    assert out[0]["yaml_path"] == ".gitlab-ci.yml"
    assert out[0]["yaml_path_source"] == "convencion"


def test_gitlab_sin_corridas_es_never_ran():
    client = make_fake_gitlab(project_body={}, pipelines=[])
    out, _meta = _gitlab_provider(client).list_pipeline_definitions()
    assert out[0]["last_run"]["status"] == "never_ran"


def test_gitlab_toma_la_corrida_mas_reciente():
    runs = [
        {"id": 3, "status": "success", "ref": "main", "web_url": "u3", "updated_at": "t3"},
        {"id": 2, "status": "failed", "ref": "main", "web_url": "u2", "updated_at": "t2"},
        {"id": 1, "status": "failed", "ref": "main", "web_url": "u1", "updated_at": "t1"},
    ]
    client = make_fake_gitlab(project_body={}, pipelines=runs)
    out, _meta = _gitlab_provider(client).list_pipeline_definitions()
    assert out[0]["last_run"]["run_id"] == "3"
    assert out[0]["last_run"]["web_url"] == "u3"
    assert out[0]["last_run"]["at"] == "t3"


def test_gitlab_exactamente_dos_llamadas_a_request():
    client = make_fake_gitlab(project_body={}, pipelines=[{"id": 1, "status": "success"}])
    _gitlab_provider(client).list_pipeline_definitions()
    assert len(client.calls) == 2


def test_gitlab_no_usa_fetch_pipelines(monkeypatch):
    """Centinela permanente contra la regresion del paginador (hasta 40 GET)."""
    from services import gitlab_provider as gp

    def _prohibido(self, ref=None):
        raise AssertionError("prohibido: pagina hasta 40")

    monkeypatch.setattr(gp.GitLabTrackerProvider, "fetch_pipelines", _prohibido)
    client = make_fake_gitlab(project_body={}, pipelines=[{"id": 1, "status": "success"}])
    out, meta = _gitlab_provider(client).list_pipeline_definitions()
    assert meta["available"] is True
    assert out


def test_gitlab_status_desconocido_no_rompe_la_fuente():
    client = make_fake_gitlab(
        project_body={}, pipelines=[{"id": 9, "status": "waiting_for_resource"}]
    )
    out, meta = _gitlab_provider(client).list_pipeline_definitions()
    assert meta["available"] is True
    assert out[0]["last_run"]["status"] == "unknown"
    assert out[0]["last_run"]["status_detail"] == "waiting_for_resource"


# ═══════════════════════════ F3 — build_inventory ═══════════════════════════════

class _FakeProvider:
    def __init__(self, name="azure_devops", registered=None, meta=None, boom=False):
        self.name = name
        self._registered = registered or []
        self._meta = meta if meta is not None else {"available": True}
        self._boom = boom

    def list_pipeline_definitions(self):
        if self._boom:
            raise RuntimeError("proveedor caido")
        return list(self._registered), dict(self._meta)


class _ProviderSinMetodo:
    name = "azure_devops"


def _reg(**kw):
    base = {
        "provider": "azure_devops",
        "name": "CI",
        "yaml_path": "pipelines/ci.yml",
        "default_branch": "main",
        "definition_id": "7",
        "source": pi.SOURCE_ADO_DEFINITIONS,
    }
    base.update(kw)
    return base


def _patch_scan(monkeypatch, files, meta):
    monkeypatch.setattr(pi, "scan_repo_pipelines", lambda root: (list(files), dict(meta)))


def _patch_root(monkeypatch, value="C:/repo"):
    import runtime_paths

    monkeypatch.setattr(runtime_paths, "_active_workspace_root", lambda: value)


def _patch_provider(monkeypatch, provider=None, exc=None):
    from services import ci_provider

    def _factory(project=None):
        if exc is not None:
            raise exc
        return provider

    monkeypatch.setattr(ci_provider, "get_ci_provider", _factory)


_META_SCAN_OK = {
    "available": True, "reason": "", "scanned_files": 3, "matched": 1,
    "truncated": False, "skipped_too_big": 0, "skipped_unparseable": 0, "root": "C:/repo",
}
_FILE_HUERFANO = {
    "provider": "azure_devops", "name": "huerfana", "yaml_path": "pipelines/huerfana.yml",
    "default_branch": None, "definition_id": None,
    "trigger": {"kind": "default", "source": "yaml"}, "source": pi.SOURCE_REPO_SCAN,
}


def test_build_inventory_sin_proveedor_no_lanza(monkeypatch):
    _patch_provider(monkeypatch, exc=TrackerConfigError("gitlab deshabilitado"))
    _patch_root(monkeypatch)
    _patch_scan(monkeypatch, [_FILE_HUERFANO], _META_SCAN_OK)
    payload = pi.build_inventory(None)
    assert payload["ok"] is True
    assert payload["sources"][0]["available"] is False
    assert any(e["category"] == "en_repo_sin_registrar" for e in payload["pipelines"])


def test_build_inventory_sin_metodo_opcional_degrada(monkeypatch):
    _patch_provider(monkeypatch, provider=_ProviderSinMetodo())
    _patch_root(monkeypatch)
    _patch_scan(monkeypatch, [], _META_SCAN_OK)
    payload = pi.build_inventory(None)
    assert payload["sources"][0]["available"] is False
    assert payload["sources"][0]["capability"] == "list_pipeline_definitions"


def test_build_inventory_sin_workspace_degrada(monkeypatch):
    _patch_provider(monkeypatch, provider=_FakeProvider())
    _patch_root(monkeypatch, value=None)
    payload = pi.build_inventory(None)
    assert payload["sources"][1]["available"] is False


def test_build_inventory_sin_workspace_no_pinta_todo_rojo(monkeypatch):
    regs = [_reg(definition_id=str(i), yaml_path=f"pipelines/ci{i}.yml") for i in (1, 2, 3)]
    _patch_provider(monkeypatch, provider=_FakeProvider(registered=regs))
    _patch_root(monkeypatch, value=None)
    payload = pi.build_inventory(None)
    assert payload["counts"]["registrada_sin_archivo"] == 0
    assert payload["counts"]["registrada_estado_desconocido"] == 3


def test_build_inventory_scan_truncado_tampoco_pinta_rojo(monkeypatch):
    regs = [_reg(definition_id=str(i), yaml_path=f"pipelines/ci{i}.yml") for i in (1, 2, 3)]
    _patch_provider(monkeypatch, provider=_FakeProvider(registered=regs))
    _patch_root(monkeypatch)
    _patch_scan(monkeypatch, [], {**_META_SCAN_OK, "truncated": True, "matched": 0})
    payload = pi.build_inventory(None)
    assert payload["counts"]["registrada_sin_archivo"] == 0
    assert payload["counts"]["registrada_estado_desconocido"] == 3


def test_build_inventory_expone_la_truncacion_en_sources(monkeypatch):
    _patch_provider(
        monkeypatch,
        provider=_FakeProvider(meta={"available": True, "capped": True, "hydrated": 10}),
    )
    _patch_root(monkeypatch)
    _patch_scan(monkeypatch, [], {**_META_SCAN_OK, "truncated": True, "matched": 0})
    payload = pi.build_inventory(None)
    assert payload["sources"][0]["capped"] is True
    assert payload["sources"][1]["truncated"] is True


def test_build_inventory_agrega_hints(monkeypatch):
    reg = _reg(yaml_path="pipelines/ci-online.yml", definition_id="7", name="CI Online")
    archivo = {
        "provider": "gitlab", "name": "ci_online", "yaml_path": "pipelines/ci_online.yml",
        "default_branch": None, "definition_id": None,
        "trigger": {"kind": "ci", "source": "yaml"}, "source": pi.SOURCE_REPO_SCAN,
    }
    _patch_provider(monkeypatch, provider=_FakeProvider(registered=[reg]))
    _patch_root(monkeypatch)
    _patch_scan(monkeypatch, [archivo], {**_META_SCAN_OK, "matched": 1})
    payload = pi.build_inventory(None)
    por_cat = {e["category"]: e for e in payload["pipelines"]}
    assert "pipelines/ci_online.yml" in por_cat["registrada_sin_archivo"]["hints"]
    assert "pipelines/ci-online.yml" in por_cat["en_repo_sin_registrar"]["hints"]


def test_build_inventory_las_dos_fuentes_caidas_sigue_200(monkeypatch):
    _patch_provider(monkeypatch, exc=TrackerConfigError("sin tracker"))
    _patch_root(monkeypatch, value=None)
    payload = pi.build_inventory(None)
    assert payload["ok"] is True
    assert payload["pipelines"] == []
    assert payload["counts"]["total"] == 0
    assert all(s["available"] is False for s in payload["sources"])


@pytest.mark.parametrize("caso", ["provider_factory", "lister", "scan", "root", "provider_name"])
def test_build_inventory_nunca_lanza(monkeypatch, caso):
    if caso == "provider_factory":
        _patch_provider(monkeypatch, exc=RuntimeError("boom"))
        _patch_root(monkeypatch)
        _patch_scan(monkeypatch, [], _META_SCAN_OK)
    elif caso == "lister":
        _patch_provider(monkeypatch, provider=_FakeProvider(boom=True))
        _patch_root(monkeypatch)
        _patch_scan(monkeypatch, [], _META_SCAN_OK)
    elif caso == "scan":
        _patch_provider(monkeypatch, provider=_FakeProvider())
        _patch_root(monkeypatch)
        def _boom(root):
            raise OSError("disco roto")
        monkeypatch.setattr(pi, "scan_repo_pipelines", _boom)
    elif caso == "root":
        _patch_provider(monkeypatch, provider=_FakeProvider())
        import runtime_paths
        def _boom_root():
            raise RuntimeError("sin workspace")
        monkeypatch.setattr(runtime_paths, "_active_workspace_root", _boom_root)
    else:
        class _Raro:
            @property
            def name(self):
                raise RuntimeError("name explota")

            def list_pipeline_definitions(self):
                return [], {"available": True}

        _patch_provider(monkeypatch, provider=_Raro())
        _patch_root(monkeypatch)
        _patch_scan(monkeypatch, [], _META_SCAN_OK)

    payload = pi.build_inventory(None)
    assert payload["ok"] is True
    assert isinstance(payload["pipelines"], list)


def test_build_inventory_cachea_y_refresh_saltea(monkeypatch):
    llamadas = {"n": 0}

    class _Contador(_FakeProvider):
        def list_pipeline_definitions(self):
            llamadas["n"] += 1
            return [], {"available": True}

    _patch_provider(monkeypatch, provider=_Contador())
    _patch_root(monkeypatch)
    _patch_scan(monkeypatch, [], _META_SCAN_OK)

    first = pi.build_inventory("P")
    assert first["cached"] is False
    assert llamadas["n"] == 1
    second = pi.build_inventory("P")
    assert second["cached"] is True
    assert llamadas["n"] == 1
    third = pi.build_inventory("P", refresh=True)
    assert third["cached"] is False
    assert llamadas["n"] == 2


def test_build_inventory_payload_tiene_las_ocho_claves(monkeypatch):
    _patch_provider(monkeypatch, provider=_FakeProvider())
    _patch_root(monkeypatch)
    _patch_scan(monkeypatch, [], _META_SCAN_OK)
    payload = pi.build_inventory(None)
    assert set(payload) == {
        "ok", "generated_at", "cached", "cache_age_sec", "project",
        "counts", "sources", "pipelines",
    }


def test_build_inventory_es_determinista(monkeypatch):
    regs = [_reg(definition_id=str(i), yaml_path=f"pipelines/ci{i}.yml") for i in (1, 2, 3)]
    _patch_provider(monkeypatch, provider=_FakeProvider(registered=regs))
    _patch_root(monkeypatch)
    _patch_scan(monkeypatch, [_FILE_HUERFANO], _META_SCAN_OK)
    a = pi.build_inventory(None)
    pi.clear_cache()
    b = pi.build_inventory(None)
    assert json.dumps(a["pipelines"], sort_keys=True, default=list) == json.dumps(
        b["pipelines"], sort_keys=True, default=list
    )


@pytest.mark.parametrize("nombre", ["azure_devops", "gitlab"])
def test_build_inventory_siempre_dos_fuentes(monkeypatch, nombre):
    _patch_provider(monkeypatch, provider=_FakeProvider(name=nombre))
    _patch_root(monkeypatch)
    _patch_scan(monkeypatch, [], _META_SCAN_OK)
    payload = pi.build_inventory(None)
    assert len(payload["sources"]) == 2
    assert payload["sources"][1]["id"] == "repo_scan"
