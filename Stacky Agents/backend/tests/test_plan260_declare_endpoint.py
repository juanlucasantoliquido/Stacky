"""Plan 260 F3 — endpoint /declare con HITL y escritura por el puerto del 94.

/declare crea, con valor VACIO, los nombres que la matriz detecto como
faltantes, previa confirmacion explicita. /declare-preview es SOLO LECTURA
y proyecta el pendiente visible posterior (ADICION 3, KPI-2).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.pipeline_environments import PROVIDER_ADO, PROVIDER_GITLAB, Requirement

RUTA_DECLARE = "/api/pipeline-environments/declare"
RUTA_PREVIEW = "/api/pipeline-environments/declare-preview"

CORPUS_PATH = Path(__file__).resolve().parent / "plan260_corpus" / "declare_matrix.json"
CORPUS = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))["rows"]


def _req(name, kind="variable", is_secret=False, provider=PROVIDER_ADO, confidence="alta"):
    return Requirement(
        name=name, kind=kind, provider=provider, is_secret=is_secret,
        declared_default=None, per_environment=True, confidence=confidence, evidence=(),
    )


class _ProviderFake:
    def __init__(self, items, name="fake"):
        self._items = list(items)
        self.name = name
        self.set_calls: list = []
        self.set_side_effects: dict = {}
        self.set_results: dict = {}

    def list_variables_scoped(self):
        return list(self._items)

    def list_variables(self):
        return [{k: v for k, v in it.items() if k != "environment_scope"} for it in self._items]

    def set_variable(self, key, value, secret):
        self.set_calls.append((key, value, secret))
        if key in self.set_side_effects:
            raise self.set_side_effects[key]
        if key in self.set_results:
            return self.set_results[key]
        return {"key": key, "is_secret": secret, "masked": secret}


@pytest.fixture
def app():
    from app import create_app

    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _flags_on(monkeypatch, tmp_path):
    import config as cfg
    import runtime_paths

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_ENV_MATRIX_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_ENV_DECLARE_ENABLED", True, raising=False)
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    yield


def _mock_provider(monkeypatch, provider):
    from services import ci_variables

    monkeypatch.setattr(ci_variables, "get_variables_provider", lambda project=None: provider)
    return provider


def _mock_requirements(monkeypatch, reqs, envs=("prod",)):
    import api.pipeline_environments as mod

    monkeypatch.setattr(mod, "extract_requirements", lambda yaml_text, provider: tuple(reqs))
    monkeypatch.setattr(mod, "derive_environments", lambda yaml_text, provider, *a: tuple(envs))


def _body(provider="azure_devops", **extra):
    base = {"yaml_text": "trigger: main\n", "provider": provider, "project": "P"}
    base.update(extra)
    return base


# ── 1 ────────────────────────────────────────────────────────────────────────
def test_f3_flag_off_404(client, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_ENV_DECLARE_ENABLED", False, raising=False)
    _mock_provider(monkeypatch, _ProviderFake([]))
    _mock_requirements(monkeypatch, [_req("X")])
    r = client.post(RUTA_DECLARE, json=_body(confirm=True))
    assert r.status_code == 404


# ── 2 ────────────────────────────────────────────────────────────────────────
def test_f3_flag_declare_off_pero_matriz_on_da_404(client, monkeypatch):
    """(v2, C5) La flag de la MATRIZ sigue ON; solo la de DECLARAR esta OFF."""
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_ENV_MATRIX_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_ENV_DECLARE_ENABLED", False, raising=False)
    prov = _mock_provider(monkeypatch, _ProviderFake([]))
    _mock_requirements(monkeypatch, [_req("X")])
    r = client.post(RUTA_DECLARE, json=_body(confirm=True))
    assert r.status_code == 404
    assert prov.set_calls == []


# ── 3 ────────────────────────────────────────────────────────────────────────
def test_f3_sin_confirm_400_y_no_escribe(client, monkeypatch):
    prov = _mock_provider(monkeypatch, _ProviderFake([]))
    _mock_requirements(monkeypatch, [_req("X")])
    r = client.post(RUTA_DECLARE, json=_body())
    assert r.status_code == 400
    assert prov.set_calls == []


# ── 4 ────────────────────────────────────────────────────────────────────────
def test_f3_preview_no_escribe(client, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_ENV_DECLARE_ENABLED", False, raising=False)
    prov = _mock_provider(monkeypatch, _ProviderFake([]))
    _mock_requirements(monkeypatch, [_req("X")])
    r = client.post(RUTA_PREVIEW, json=_body())
    assert r.status_code == 200
    assert prov.set_calls == []


# ── 5 ────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("row", CORPUS, ids=lambda r: f"{r['provider']}-{r['kind']}")
def test_f3_preview_proyecta_el_mismo_pendiente_visible(client, monkeypatch, row):
    _mock_provider(monkeypatch, _ProviderFake([]))
    req = _req("K", kind=row["kind"], is_secret=row["declared_secret"], provider=row["provider"])
    _mock_requirements(monkeypatch, [req])
    r = client.post(RUTA_PREVIEW, json=_body(provider=row["provider"]))
    assert r.status_code == 200
    data = r.get_json()
    assert data["pendiente_visible_actual"] == data["pendiente_visible_proyectado"] == 1


# ── 6 ────────────────────────────────────────────────────────────────────────
def test_f3_proyeccion_ado_secreto_es_none():
    """(v3, C1) La proyeccion NO es 'marcar todo has_value=False'. Se cae si
    alguien vuelve a proyectar False para todo (incl. ADO+secreto)."""
    from services.pipeline_env_declare import proyectar_has_value

    assert proyectar_has_value(PROVIDER_ADO, True) is None
    assert proyectar_has_value(PROVIDER_ADO, False) is False
    assert proyectar_has_value(PROVIDER_GITLAB, True) is False
    assert proyectar_has_value(PROVIDER_GITLAB, False) is False


# ── 7 ────────────────────────────────────────────────────────────────────────
def test_f3_declara_con_valor_vacio(client, monkeypatch):
    prov = _mock_provider(monkeypatch, _ProviderFake([]))
    _mock_requirements(monkeypatch, [_req("NUEVA")])
    r = client.post(RUTA_DECLARE, json=_body(confirm=True))
    assert r.status_code == 200
    assert prov.set_calls, "no se llamo a set_variable"
    for _key, value, _secret in prov.set_calls:
        assert value == ""


# ── 8 ────────────────────────────────────────────────────────────────────────
def test_f3_nunca_pisa_una_variable_con_valor(client, monkeypatch):
    prov = _mock_provider(monkeypatch, _ProviderFake([
        {"key": "YA_CARGADA", "has_value": True, "environment_scope": "*"},
    ]))
    _mock_requirements(monkeypatch, [_req("YA_CARGADA")])
    r = client.post(RUTA_DECLARE, json=_body(confirm=True))
    assert r.status_code == 200
    assert prov.set_calls == []
    assert r.get_json()["declared"] == []


# ── 9 ────────────────────────────────────────────────────────────────────────
def test_f3_una_falla_no_aborta_el_lote(client, monkeypatch):
    from services.tracker_provider import TrackerApiError

    prov = _mock_provider(monkeypatch, _ProviderFake([]))
    prov.set_side_effects["B"] = TrackerApiError(500, "boom", kind="internal_error")
    _mock_requirements(monkeypatch, [_req("A"), _req("B"), _req("C")])
    r = client.post(RUTA_DECLARE, json=_body(confirm=True))
    assert r.status_code == 200
    data = r.get_json()
    assert len(data["declared"]) == 2
    assert len(data["failed"]) == 1
    assert data["failed"][0]["key"] == "B"


# ── 10 ───────────────────────────────────────────────────────────────────────
def test_f3_gitlab_masked_false_va_a_needs_masking(client, monkeypatch):
    prov = _mock_provider(monkeypatch, _ProviderFake([]))
    prov.set_results["SECRETO"] = {"key": "SECRETO", "is_secret": True, "masked": False}
    _mock_requirements(monkeypatch, [_req("SECRETO", kind="secret", is_secret=True,
                                          provider=PROVIDER_GITLAB)])
    r = client.post(RUTA_DECLARE, json=_body(provider="gitlab", confirm=True))
    assert r.status_code == 200
    assert "SECRETO" in r.get_json()["needs_masking"]


# ── 11 ───────────────────────────────────────────────────────────────────────
def test_f3_ado_sin_definition_da_409_y_no_escribe(client, monkeypatch):
    from services import ci_variables

    def _raise(project=None):
        raise ci_variables.VariablesUnavailableError(
            "ADO sin pipeline definition para azure-pipelines.yml")

    monkeypatch.setattr(ci_variables, "get_variables_provider", _raise)
    _mock_requirements(monkeypatch, [_req("X")])
    r = client.post(RUTA_DECLARE, json=_body(confirm=True))
    assert r.status_code == 409
    assert r.get_json()["error"] == "proveedor_sin_variables"


# ── 12 ───────────────────────────────────────────────────────────────────────
def test_f3_mensaje_de_error_sanitizado(client, monkeypatch):
    prov = _mock_provider(monkeypatch, _ProviderFake([]))
    prov.set_side_effects["X"] = RuntimeError("boom S3cr3t!XYZ")
    _mock_requirements(monkeypatch, [_req("X")])
    r = client.post(RUTA_DECLARE, json=_body(confirm=True))
    assert r.status_code == 200
    cuerpo = r.get_data(as_text=True)
    assert "S3cr3t!XYZ" not in cuerpo


# ── 13 ───────────────────────────────────────────────────────────────────────
def test_f3_ningun_valor_en_la_respuesta(client, monkeypatch):
    secreto = "Xk7#pQ2mZr9Lw4Tv"
    _mock_provider(monkeypatch, _ProviderFake([
        {"key": "OTRA", "has_value": True, "value": secreto, "environment_scope": "*"},
    ]))
    _mock_requirements(monkeypatch, [_req("OTRA"), _req("NUEVA")])
    r = client.post(RUTA_PREVIEW, json=_body())
    assert secreto not in r.get_data(as_text=True)


# ── 14 ───────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("row", CORPUS, ids=lambda r: f"{r['provider']}-{r['kind']}")
def test_f3_pendiente_visible_no_baja_al_declarar(client, monkeypatch, row):
    """KPI-2, el corazon del plan. Los 4 casos proveedor x kind, obligatorio
    incluido (azure_devops, secret): el caso facil (gitlab+variable) no basta."""
    prov = _mock_provider(monkeypatch, _ProviderFake([]))
    req = _req("K", kind=row["kind"], is_secret=row["declared_secret"], provider=row["provider"])
    _mock_requirements(monkeypatch, [req])

    r0 = client.post(RUTA_PREVIEW, json=_body(provider=row["provider"]))
    antes = r0.get_json()["pendiente_visible_actual"]

    r1 = client.post(RUTA_DECLARE, json=_body(provider=row["provider"], confirm=True))
    assert r1.status_code == 200
    despues = r1.get_json()["pendiente_visible_after"]

    assert despues == antes, f"{row['provider']}/{row['kind']}: bajo de {antes} a {despues}"


# ── 15 ───────────────────────────────────────────────────────────────────────
def test_f3_ado_secreto_declarado_no_apaga_el_titular(client, monkeypatch):
    """(v3, C1) Control de punta a punta del bug de §2.5."""
    _mock_provider(monkeypatch, _ProviderFake([]))
    _mock_requirements(monkeypatch, [_req("SONAR_TOKEN", kind="secret", is_secret=True,
                                          provider=PROVIDER_ADO)])
    r = client.post(RUTA_DECLARE, json=_body(confirm=True))
    assert r.status_code == 200
    data = r.get_json()
    assert data["pending_count_after"] == 0
    assert data["pendiente_visible_after"] == 1


# ── 16 ───────────────────────────────────────────────────────────────────────
def test_f3_keys_fuera_del_plan_se_rechazan_con_400(client, monkeypatch):
    prov = _mock_provider(monkeypatch, _ProviderFake([]))
    _mock_requirements(monkeypatch, [_req("A")])
    r = client.post(RUTA_DECLARE, json=_body(confirm=True, keys=["A", "NO_EXISTE"]))
    assert r.status_code == 400
    assert r.get_json()["error"] == "keys_fuera_del_plan"
    assert prov.set_calls == []
