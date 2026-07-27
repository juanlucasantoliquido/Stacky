"""Plan 202 E7 — flags del arnés, superficie HTTP y kill-switch de un clic."""
from __future__ import annotations

import pytest

BASE = "/api/night-foundry"


@pytest.fixture
def app():
    from app import create_app

    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture(autouse=True)
def _entorno(monkeypatch, tmp_path):
    import config as cfg
    import runtime_paths

    from services import night_foundry_ledger as L

    monkeypatch.setattr(cfg.config, "STACKY_NIGHT_FOUNDRY_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_NIGHT_FOUNDRY_TOKEN_BUDGET", 40000, raising=False)
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    for env in ("STACKY_NIGHT_FOUNDRY_HARD_DISABLE", "STACKY_EVOLUTION_HARD_DISABLE"):
        monkeypatch.delenv(env, raising=False)
    L.reset_inflight()
    yield tmp_path
    L.reset_inflight()


# ═══════════════════ flags del arnés ═════════════════════════════════════════

def test_flag_maestra_registrada_y_default_off():
    """Default OFF por EXCEPCION DURA #3 (prerequisito no garantizado): la Fragua
    necesita el arbol de desarrollo y su turno depende de /loop, propio de Claude
    Code. Una flag default-OFF NO declara `default=` en su FlagSpec (eso la volveria
    `default_is_known` y rompe test_default_known_only_for_curated)."""
    import config as cfg
    from services.harness_flags import FLAG_REGISTRY, default_is_known

    spec = {s.key: s for s in FLAG_REGISTRY}["STACKY_NIGHT_FOUNDRY_ENABLED"]
    assert spec.type == "bool"
    assert spec.default is None, "una flag default-OFF no declara default= en la FlagSpec"
    assert default_is_known(spec) is False
    # el default EFECTIVO vive en config.py y es OFF
    assert type(cfg.config).STACKY_NIGHT_FOUNDRY_ENABLED is False or \
        cfg.Config.STACKY_NIGHT_FOUNDRY_ENABLED is False


def test_flag_budget_registrada_con_bounds_y_requires():
    from services.harness_flags import FLAG_REGISTRY, default_is_known

    spec = {s.key: s for s in FLAG_REGISTRY}["STACKY_NIGHT_FOUNDRY_TOKEN_BUDGET"]
    assert spec.type == "int"
    assert (spec.min_value, spec.max_value) == (1000, 500000)
    assert spec.requires == "STACKY_NIGHT_FOUNDRY_ENABLED"
    assert default_is_known(spec) is False


def test_ambas_flags_categorizadas():
    from services.harness_flags import _CATEGORY_KEYS

    todas = {k for keys in _CATEGORY_KEYS.values() for k in keys}
    assert "STACKY_NIGHT_FOUNDRY_ENABLED" in todas
    assert "STACKY_NIGHT_FOUNDRY_TOKEN_BUDGET" in todas


def test_ambas_flags_con_ayuda_llana_para_la_ui():
    """La flag se activa DESDE LA UI: el panel del arnés es genérico y solo muestra
    lo que está en el registro, con su ayuda en castellano llano."""
    from services.harness_flags_help import plain_help_for

    for key in ("STACKY_NIGHT_FOUNDRY_ENABLED", "STACKY_NIGHT_FOUNDRY_TOKEN_BUDGET"):
        ayuda = plain_help_for(key)
        assert ayuda is not None, key
        assert set(ayuda) == {"what", "on_effect", "off_effect", "example"}


def test_flags_visibles_en_read_current():
    from services.harness_flags import read_current

    por_key = {f["key"]: f for f in read_current()}
    for key in ("STACKY_NIGHT_FOUNDRY_ENABLED", "STACKY_NIGHT_FOUNDRY_TOKEN_BUDGET"):
        assert key in por_key, f"{key} no llega al panel del arnés"
        assert por_key[key]["plain_help"] is not None


# ═══════════════════ KPI-9 · costo ocioso 0 ══════════════════════════════════

def test_ningun_hook_de_arranque_invoca_la_fragua():
    """KPI-9: con la flag ON pero sin turno armado, NADA consume. Ningún daemon ni
    hook de arranque puede tocar el orquestador."""
    from pathlib import Path

    import runtime_paths

    raiz = Path(runtime_paths.backend_root())
    for nombre in ("app.py", "harness/post_run.py", "services/ticket_status.py"):
        p = raiz / nombre
        if not p.exists():
            continue
        assert "night_foundry" not in p.read_text(encoding="utf-8", errors="replace"), (
            f"{nombre} referencia la Fragua: eso seria autonomia no pedida")


# ═══════════════════ superficie HTTP ═════════════════════════════════════════

def test_endpoints_404_con_flag_off(app, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_NIGHT_FOUNDRY_ENABLED", False, raising=False)
    c = app.test_client()
    assert c.get(BASE + "/status").status_code == 404
    assert c.get(BASE + "/digest/latest").status_code == 404
    assert c.get(BASE + "/ledger").status_code == 404
    assert c.post(BASE + "/run-one-turn", json={"plan": False}).status_code == 404
    assert c.post(BASE + "/stop").status_code == 404
    assert c.delete(BASE + "/stop").status_code == 404


def test_status_ok_con_flag_on(app):
    r = app.test_client().get(BASE + "/status")
    assert r.status_code == 200
    d = r.get_json()
    assert d["availability"]["available"] is True
    assert d["budget_tokens"] == 40000
    assert d["stopped"] is False
    assert "backlog" in d


def test_status_expone_no_disponible_en_congelado(app, monkeypatch):
    """El operador tiene que VER por qué la Fragua no corre; nunca un silencio."""
    import runtime_paths

    monkeypatch.setattr(runtime_paths, "is_frozen", lambda: True)
    d = app.test_client().get(BASE + "/status").get_json()
    assert d["availability"]["available"] is False
    assert d["availability"]["reason_code"] == "frozen_deploy"
    assert d["availability"]["reason"]


def test_digest_latest_vacio_y_luego_con_contenido(app, _entorno):
    from services import night_foundry_digest as D
    from services import night_foundry_ledger as L

    c = app.test_client()
    assert c.get(BASE + "/digest/latest").get_json()["digest"] == {}

    it = L.upsert_item("package", "plan:1", L.compute_input_hash("package", "plan:1", "s"),
                       night="2026-07-26")
    L.record_result(it["id"], "done", output_ref="packages/p.json")
    D.build_digest("2026-07-26", budget=40000, stopped_reason="queue_empty")
    d = c.get(BASE + "/digest/latest").get_json()["digest"]
    assert d["night"] == "2026-07-26" and len(d["decisions"]) == 1


def test_ledger_route_filtra_por_noche(app):
    from services import night_foundry_ledger as L

    L.upsert_item("package", "plan:1", L.compute_input_hash("package", "plan:1", "s"),
                  night="2026-07-26")
    L.upsert_item("package", "plan:2", L.compute_input_hash("package", "plan:2", "s"),
                  night="2026-07-20")
    items = app.test_client().get(BASE + "/ledger?night=2026-07-26").get_json()["items"]
    assert [i["target"] for i in items] == ["plan:1"]


def test_stop_endpoint_crea_y_borra_stop(app, _entorno):
    """Kill-switch de un clic: SOLO detiene y reanuda; nunca arranca autonomía."""
    c = app.test_client()
    stop = _entorno / "night_foundry" / "STOP"
    assert c.post(BASE + "/stop").get_json() == {"stopped": True}
    assert stop.exists()
    assert c.get(BASE + "/status").get_json()["stopped"] is True
    assert c.delete(BASE + "/stop").get_json() == {"stopped": False}
    assert not stop.exists()
    assert c.delete(BASE + "/stop").status_code == 200  # idempotente


def test_run_one_turn_respeta_el_stop(app, _entorno):
    c = app.test_client()
    c.post(BASE + "/stop")
    d = c.post(BASE + "/run-one-turn", json={"plan": False}).get_json()
    assert d["processed"] is None and d["reason"] == "stop_file"


def test_run_one_turn_409_en_congelado(app, monkeypatch):
    import runtime_paths

    monkeypatch.setattr(runtime_paths, "is_frozen", lambda: True)
    r = app.test_client().post(BASE + "/run-one-turn", json={"plan": False})
    assert r.status_code == 409
    assert r.get_json()["reason"] == "frozen_deploy"


def test_run_one_turn_cola_vacia(app):
    d = app.test_client().post(BASE + "/run-one-turn", json={"plan": False}).get_json()
    assert d["ok"] is True and d["processed"] is None and d["reason"] == "queue_empty"


def test_run_one_turn_procesa_un_item_determinista(app, _entorno):
    import datetime as _dt

    from services import night_foundry_ledger as L

    noche = f"{_dt.datetime.now(_dt.timezone.utc):%Y-%m-%d}"
    item = L.upsert_item("package", "plan:202",
                         L.compute_input_hash("package", "plan:202", "s"), night=noche)
    d = app.test_client().post(BASE + "/run-one-turn", json={"plan": False}).get_json()
    assert d["processed"] == item["id"]
    assert d["state"] == "done" and d["lane"] == "package"
    assert d["output_ref"].startswith("packages/")
    assert (_entorno / "night_foundry" / d["output_ref"]).exists()


def test_run_one_turn_no_ejecuta_critic(app):
    """El carril de crítica necesita el runtime Claude: no se finge que corrió."""
    import datetime as _dt

    from services import night_foundry_ledger as L

    noche = f"{_dt.datetime.now(_dt.timezone.utc):%Y-%m-%d}"
    L.upsert_item("critic", "plan:900", L.compute_input_hash("critic", "plan:900", "s"),
                  night=noche)
    d = app.test_client().post(BASE + "/run-one-turn", json={"plan": False}).get_json()
    assert d["processed"] is None and d["reason"] == "critic_necesita_claude"
    fila = [r for r in L.list_items(night=noche) if r["target"] == "plan:900"][0]
    assert fila["state"] == "pending"
