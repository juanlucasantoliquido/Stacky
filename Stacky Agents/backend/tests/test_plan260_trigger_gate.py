"""Plan 260 F4 — el gate antes de disparar.

POST /api/ci/<project>/trigger no dispara a ciegas, y JAMAS frena un disparo
por no haber podido averiguar (nunca bloquear por ignorancia). El gate corre
DESPUES de get_ci_provider y ANTES de la idempotencia, para no consumir la
ventana de 60s con un disparo que se va a rechazar.
"""
from __future__ import annotations

import json
import time as _time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import config
from services.pipeline_environments import PROVIDER_ADO, PROVIDER_GITLAB, Requirement

CORPUS_PATH = Path(__file__).resolve().parent / "plan260_corpus" / "declare_matrix.json"
CORPUS = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))["rows"]


def _req(name, kind="variable", is_secret=False, provider=PROVIDER_ADO, confidence="alta"):
    return Requirement(
        name=name, kind=kind, provider=provider, is_secret=is_secret,
        declared_default=None, per_environment=True, confidence=confidence, evidence=(),
    )


@pytest.fixture()
def app():
    from app import create_app

    _app = create_app()
    _app.config["TESTING"] = True
    return _app


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_stores(monkeypatch, tmp_path):
    import api.ci as ci_mod
    import runtime_paths

    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    ci_mod._RECENT_TRIGGERS.clear()
    ci_mod._ACTIVE_POLLS.clear()
    ci_mod._RECENT_READINESS.clear()
    yield
    ci_mod._RECENT_TRIGGERS.clear()
    ci_mod._ACTIVE_POLLS.clear()
    ci_mod._RECENT_READINESS.clear()


def _mock_provider(tracker_type: str = "azure_devops") -> MagicMock:
    mock = MagicMock()
    mock.name = tracker_type
    mock.trigger_pipeline.return_value = {
        "id": "42", "status": "created", "ref": "develop", "sha": "abc123",
        "web_url": "http://x/42",
    }
    mock.last_pipeline_for_ref.return_value = None
    return mock


def _flags_on(monkeypatch, gate=True):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", True)
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_TRIGGER_ENV_GATE_ENABLED", gate)


def _sin_requisitos(monkeypatch):
    """Ninguna key requerida: la matriz siempre da 'ok'."""
    import api.ci as ci_mod
    monkeypatch.setattr(ci_mod, "extract_requirements", lambda *a, **kw: ())
    monkeypatch.setattr(ci_mod, "derive_environments", lambda *a, **kw: ("prod",))


def _con_requisito_faltante(monkeypatch, req):
    import api.ci as ci_mod
    monkeypatch.setattr(ci_mod, "extract_requirements", lambda *a, **kw: (req,))
    monkeypatch.setattr(ci_mod, "derive_environments", lambda *a, **kw: ("prod",))


def _post_trigger(client, **body_extra):
    body = {"confirm": True, "ref": "develop", "yaml_text": "trigger: main\n"}
    body.update(body_extra)
    return client.post("/api/ci/myproject/trigger", json=body)


# ── 1 ────────────────────────────────────────────────────────────────────────
def test_f4_evaluate_readiness_puro():
    from pathlib import Path as _P

    src = (_P(__file__).resolve().parent.parent / "services" / "ci_env_gate.py").read_text(
        encoding="utf-8")
    assert "import requests" not in src
    assert "datetime.now(" not in src, "no debe llamar datetime.now(): no determinista"
    assert re_no_flask(src)


def re_no_flask(src: str) -> bool:
    return "from flask" not in src and "import flask" not in src


# ── 2 ────────────────────────────────────────────────────────────────────────
def test_f4_bloquea_con_faltantes(client, monkeypatch):
    _flags_on(monkeypatch)
    _con_requisito_faltante(monkeypatch, _req("SONAR_TOKEN", kind="secret", is_secret=True))
    prov = _mock_provider()
    with patch("api.ci.get_ci_provider", return_value=prov), \
         patch("api.ci._read_pat_scopes", return_value=None):
        r = _post_trigger(client)
    assert r.status_code == 409
    data = r.get_json()
    assert data["kind"] == "env_pending"
    prov.trigger_pipeline.assert_not_called()


# ── 3 ────────────────────────────────────────────────────────────────────────
def test_f4_ack_explicito_deja_pasar(client, monkeypatch):
    _flags_on(monkeypatch)
    _con_requisito_faltante(monkeypatch, _req("SONAR_TOKEN", kind="secret", is_secret=True))
    prov = _mock_provider()
    with patch("api.ci.get_ci_provider", return_value=prov), \
         patch("api.ci._read_pat_scopes", return_value=None):
        r = _post_trigger(client, acknowledge_missing=True)
    assert r.status_code == 200
    prov.trigger_pipeline.assert_called_once()


# ── 4 ────────────────────────────────────────────────────────────────────────
def test_f4_sin_faltantes_dispara(client, monkeypatch):
    _flags_on(monkeypatch)
    _sin_requisitos(monkeypatch)
    prov = _mock_provider()
    with patch("api.ci.get_ci_provider", return_value=prov), \
         patch("api.ci._read_pat_scopes", return_value=None):
        r = _post_trigger(client)
    assert r.status_code == 200
    prov.trigger_pipeline.assert_called_once()


# ── 5 ────────────────────────────────────────────────────────────────────────
def test_f4_sin_yaml_no_bloquea(client, monkeypatch):
    import api.ci as ci_mod

    _flags_on(monkeypatch)
    monkeypatch.setattr(ci_mod, "_yaml_fuente_inventario", lambda: None)
    prov = _mock_provider()
    with patch("api.ci.get_ci_provider", return_value=prov), \
         patch("api.ci._read_pat_scopes", return_value=None):
        r = client.post("/api/ci/myproject/trigger",
                        json={"confirm": True, "ref": "develop"})  # sin yaml_text
    assert r.status_code == 200
    prov.trigger_pipeline.assert_called_once()
    assert r.get_json()["readiness"]["verdict"] == "degradado"


# ── 6 ────────────────────────────────────────────────────────────────────────
def test_f4_sin_resolver_no_bloquea_aunque_todo_sea_falta(client, monkeypatch):
    """(v2, C4) El test mas importante de la fase: sin poder resolver, degradado
    y el disparo SALE, aunque haya requirements confidence=alta que darian falta."""
    import api.ci as ci_mod

    _flags_on(monkeypatch)
    _con_requisito_faltante(monkeypatch, _req("DEPLOY_HOST", confidence="alta"))

    def _resolve_explota(*a, **kw):
        raise RuntimeError("proveedor no configurado")

    monkeypatch.setattr(ci_mod, "resolve", _resolve_explota)
    prov = _mock_provider()
    with patch("api.ci.get_ci_provider", return_value=prov), \
         patch("api.ci._read_pat_scopes", return_value=None):
        r = _post_trigger(client)
    assert r.status_code == 200
    prov.trigger_pipeline.assert_called_once()
    assert r.get_json()["readiness"]["verdict"] == "degradado"


# ── 7 ────────────────────────────────────────────────────────────────────────
def test_f4_orden_de_evaluacion():
    from services.ci_env_gate import evaluate_readiness
    from services.pipeline_environments import Cell, build_matrix

    req = _req("X")
    matriz = build_matrix((req,), ("prod",),
                          {(req.name, "prod"): ("falta", "ninguna", None)}, PROVIDER_ADO)
    assert matriz.pending_count > 0
    readiness = evaluate_readiness(matriz, resolved=False)
    assert readiness.verdict == "degradado"


# ── 8 ────────────────────────────────────────────────────────────────────────
def test_f4_timeout_de_resolucion_degrada(client, monkeypatch):
    import api.ci as ci_mod

    _flags_on(monkeypatch)
    _con_requisito_faltante(monkeypatch, _req("X"))

    def _resolve_lento(*a, **kw):
        _time.sleep(3)
        return {}, ()

    monkeypatch.setattr(ci_mod, "resolve", _resolve_lento)
    prov = _mock_provider()
    with patch("api.ci.get_ci_provider", return_value=prov), \
         patch("api.ci._read_pat_scopes", return_value=None):
        t0 = _time.monotonic()
        r = _post_trigger(client)
        elapsed = _time.monotonic() - t0

    assert elapsed < 2.0, f"el gate esperó {elapsed:.2f}s (debería cortar a 1.5s)"
    assert r.status_code == 200
    data = r.get_json()
    assert data["readiness"]["verdict"] == "degradado"
    assert data["readiness"]["elapsed_ms"] <= 1600


# ── 9 ────────────────────────────────────────────────────────────────────────
def test_f4_degradado_no_se_almacena_ni_se_reusa(client, monkeypatch):
    import api.ci as ci_mod

    _flags_on(monkeypatch)
    monkeypatch.setattr(ci_mod, "_yaml_fuente_inventario", lambda: None)
    prov = _mock_provider()
    with patch("api.ci.get_ci_provider", return_value=prov), \
         patch("api.ci._read_pat_scopes", return_value=None):
        # preview sin yaml_path -> degradado (no debe cachear nada)
        client.get("/api/ci/myproject/trigger-preview?ref=develop")
        assert ci_mod._RECENT_READINESS == {}

        # trigger CON yaml_text y faltantes reales -> 409, no un pase por reuso
        _con_requisito_faltante(monkeypatch, _req("X", confidence="alta"))
        r = _post_trigger(client)
    assert r.status_code == 409


# ── 10 ───────────────────────────────────────────────────────────────────────
def test_f4_almacen_de_veredictos_acotado(client, monkeypatch):
    import api.ci as ci_mod

    _flags_on(monkeypatch)
    _sin_requisitos(monkeypatch)
    prov = _mock_provider()
    with patch("api.ci.get_ci_provider", return_value=prov), \
         patch("api.ci._read_pat_scopes", return_value=None):
        for i in range(40):
            client.post("/api/ci/myproject/trigger", json={
                "confirm": True, "ref": f"r{i}", "yaml_text": f"trigger: r{i}\n",
            })
    assert len(ci_mod._RECENT_READINESS) <= 32

    # entrada vieja (fuera de ventana) no se reusa
    clave = next(iter(ci_mod._RECENT_READINESS))
    readiness_vieja, _ts = ci_mod._RECENT_READINESS[clave]
    ci_mod._RECENT_READINESS[clave] = (readiness_vieja, _time.monotonic() - 61)
    resultado = ci_mod._evaluar_readiness("myproject", clave[1], prov, yaml_text="trigger: r0\n")
    assert resultado.source != "preview_reusado"


# ── 11 ───────────────────────────────────────────────────────────────────────
def test_f4_desconocido_advierte_pero_no_bloquea(client, monkeypatch):
    _flags_on(monkeypatch)
    _con_requisito_faltante(monkeypatch, _req("SONAR_TOKEN", kind="secret", is_secret=True,
                                              provider=PROVIDER_ADO))
    import api.ci as ci_mod

    def _resolve_desconocido(*a, **kw):
        # el resolver "encuentra" la key pero el proveedor no puede confirmarla (ADO+secreto)
        return {(a[0][0].name, "prod"): ("manual", "declarada_sin_valor_verificable", None)}, ()

    monkeypatch.setattr(ci_mod, "resolve", _resolve_desconocido)
    prov = _mock_provider()
    with patch("api.ci.get_ci_provider", return_value=prov), \
         patch("api.ci._read_pat_scopes", return_value=None):
        r = _post_trigger(client)
    assert r.status_code == 200
    data = r.get_json()
    assert data["readiness"]["verdict"] == "advierte"
    assert data["readiness"]["pending_count"] == 0


# ── 12 ───────────────────────────────────────────────────────────────────────
def test_f4_una_excepcion_del_gate_no_rompe_el_trigger(client, monkeypatch):
    import api.ci as ci_mod

    _flags_on(monkeypatch)

    def _explota(*a, **kw):
        raise RuntimeError("bug interno del gate")

    monkeypatch.setattr(ci_mod, "extract_requirements", _explota)
    prov = _mock_provider()
    with patch("api.ci.get_ci_provider", return_value=prov), \
         patch("api.ci._read_pat_scopes", return_value=None):
        r = _post_trigger(client)
    assert r.status_code == 200
    prov.trigger_pipeline.assert_called_once()


# ── 13 ───────────────────────────────────────────────────────────────────────
def test_f4_flag_off_no_cambia_nada(client, monkeypatch):
    _flags_on(monkeypatch, gate=False)
    _con_requisito_faltante(monkeypatch, _req("SONAR_TOKEN", kind="secret", is_secret=True))
    prov = _mock_provider()
    with patch("api.ci.get_ci_provider", return_value=prov), \
         patch("api.ci._read_pat_scopes", return_value=None):
        r = _post_trigger(client)
    assert r.status_code == 200
    prov.trigger_pipeline.assert_called_once()
    assert "readiness" not in (r.get_json() or {})


# ── 14 ───────────────────────────────────────────────────────────────────────
def test_f4_el_gate_corre_antes_de_la_idempotencia(client, monkeypatch):
    import api.ci as ci_mod

    _flags_on(monkeypatch)
    _con_requisito_faltante(monkeypatch, _req("SONAR_TOKEN", kind="secret", is_secret=True))

    contador = {"n": 0}
    should_trigger_real = ci_mod.should_trigger

    def _espia(*a, **kw):
        contador["n"] += 1
        return should_trigger_real(*a, **kw)

    monkeypatch.setattr(ci_mod, "should_trigger", _espia)
    prov = _mock_provider()
    with patch("api.ci.get_ci_provider", return_value=prov), \
         patch("api.ci._read_pat_scopes", return_value=None):
        r = _post_trigger(client)
    assert r.status_code == 409
    assert contador["n"] == 0, "should_trigger no debe llamarse si el gate ya bloqueo"


# ── 15 ───────────────────────────────────────────────────────────────────────
def test_f4_ningun_valor_en_el_409(client, monkeypatch):
    _flags_on(monkeypatch)
    _con_requisito_faltante(monkeypatch, _req("SONAR_TOKEN", kind="secret", is_secret=True))
    prov = _mock_provider()
    with patch("api.ci.get_ci_provider", return_value=prov), \
         patch("api.ci._read_pat_scopes", return_value=None):
        r = _post_trigger(client)
    data = r.get_json()
    for m in data["missing"]:
        assert set(m.keys()) == {"name", "environment"}


# ── 16 ───────────────────────────────────────────────────────────────────────
def test_f4_ledger_conserva_env_ack(client, monkeypatch):
    _flags_on(monkeypatch)
    monkeypatch.setattr(config.config, "STACKY_CI_RUN_LEDGER_ENABLED", True)
    _con_requisito_faltante(monkeypatch, _req("SONAR_TOKEN", kind="secret", is_secret=True))
    prov = _mock_provider()
    with patch("api.ci.get_ci_provider", return_value=prov), \
         patch("api.ci._read_pat_scopes", return_value=None):
        r = _post_trigger(client, acknowledge_missing=True)
    assert r.status_code == 200

    from services.ci_run_ledger import list_runs
    runs = list_runs(project=None, limit=5)
    assert runs, "no se escribio ninguna corrida en el ledger"
    ultima = runs[-1]
    assert ultima.get("env_ack") is True
    assert ultima.get("pending_fingerprint")


# ── 17 ───────────────────────────────────────────────────────────────────────
def test_f4_preview_trae_readiness(client, monkeypatch):
    import api.ci as ci_mod

    _flags_on(monkeypatch)
    monkeypatch.setattr(ci_mod, "_leer_yaml_por_path", lambda p: "trigger: main\n" if p else None)
    _sin_requisitos(monkeypatch)
    prov = _mock_provider()
    with patch("api.ci.get_ci_provider", return_value=prov):
        r_con_path = client.get("/api/ci/myproject/trigger-preview?ref=develop&yaml_path=a.yml")
        assert r_con_path.status_code == 200
        assert r_con_path.get_json()["readiness"]["verdict"] == "ok"

        monkeypatch.setattr(ci_mod, "_yaml_fuente_inventario", lambda: None)
        r_sin_path = client.get("/api/ci/myproject/trigger-preview?ref=develop")
        assert r_sin_path.status_code == 200
        assert r_sin_path.get_json()["readiness"]["verdict"] == "degradado"


# ── 18 ───────────────────────────────────────────────────────────────────────
def test_f4_veredicto_reusado_declara_su_origen(client, monkeypatch):
    import api.ci as ci_mod

    _flags_on(monkeypatch)
    monkeypatch.setattr(ci_mod, "_leer_yaml_por_path", lambda p: "trigger: main\n")
    _sin_requisitos(monkeypatch)
    prov = _mock_provider()
    with patch("api.ci.get_ci_provider", return_value=prov):
        r0 = client.get("/api/ci/myproject/trigger-preview?ref=develop&yaml_path=a.yml")
        assert r0.get_json()["readiness"]["source"] == "calculado"

        with patch("api.ci._read_pat_scopes", return_value=None):
            r1 = client.post("/api/ci/myproject/trigger", json={
                "confirm": True, "ref": "develop", "yaml_text": "trigger: main\n",
            })
    assert r1.status_code == 200
    assert r1.get_json()["readiness"]["source"] == "preview_reusado"


# ── 19 ───────────────────────────────────────────────────────────────────────
def test_f4_yaml_distinto_no_reusa_el_veredicto(client, monkeypatch):
    import api.ci as ci_mod

    _flags_on(monkeypatch)
    monkeypatch.setattr(ci_mod, "_leer_yaml_por_path", lambda p: "trigger: main\n")
    _sin_requisitos(monkeypatch)
    prov = _mock_provider()
    with patch("api.ci.get_ci_provider", return_value=prov):
        client.get("/api/ci/myproject/trigger-preview?ref=develop&yaml_path=a.yml")
        with patch("api.ci._read_pat_scopes", return_value=None):
            r1 = client.post("/api/ci/myproject/trigger", json={
                "confirm": True, "ref": "develop", "yaml_text": "trigger: OTRO\n",
            })
    assert r1.get_json()["readiness"]["source"] == "calculado"


# ── 20 ───────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("row", CORPUS, ids=lambda r: f"{r['provider']}-{r['kind']}")
def test_f4_veredicto_por_fila(row):
    from services.ci_env_gate import evaluate_readiness
    from services.pipeline_environments import build_matrix

    req = _req("K", kind=row["kind"], is_secret=row["declared_secret"], provider=row["provider"])
    entrada = (row["state"], row["source"], None)
    matriz = build_matrix((req,), ("prod",), {(req.name, "prod"): entrada}, row["provider"])
    readiness = evaluate_readiness(matriz, resolved=True)
    assert readiness.verdict == row["gate"]
