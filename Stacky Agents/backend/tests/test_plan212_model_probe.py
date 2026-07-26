"""Plan 212 F6 — El catálogo se completa con lo que el CLI instalado declara.

Tres reglas duras que estos tests fijan: nunca invoca un modelo (costo de tokens
cero), nunca resta del catálogo del archivo, y nunca propaga una excepción.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import model_probe as P  # noqa: E402


class _Proc:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


def _fake_run(monkeypatch, respuestas: dict):
    """Mapea el subcomando (unido por espacios) a un resultado."""
    llamadas: list = []

    def _run(cmd, **kw):
        sub = " ".join(cmd[1:])
        llamadas.append((sub, kw))
        r = respuestas.get(sub)
        if isinstance(r, Exception):
            raise r
        return r if r is not None else _Proc(returncode=1)

    monkeypatch.setattr(subprocess, "run", _run)
    return llamadas


# ---------------------------------------------------------------------------
# extract_model_ids — el formato del listado no está documentado
# ---------------------------------------------------------------------------

def test_extrae_de_lista_de_strings():
    assert P.extract_model_ids(["a", "b"]) == ["a", "b"]


def test_extrae_de_lista_de_dicts_por_id_o_name():
    assert P.extract_model_ids([{"id": "a"}, {"name": "b"}]) == ["a", "b"]


def test_extrae_de_dict_envuelto():
    for clave in ("models", "data", "items"):
        assert P.extract_model_ids({clave: ["x"]}) == ["x"]


def test_formas_desconocidas_dan_vacio():
    for basura in (None, 42, "texto", {}, {"otra": ["x"]}, [1, 2], [{}]):
        assert P.extract_model_ids(basura) == []


# ---------------------------------------------------------------------------
# probe — costo cero y tolerancia
# ---------------------------------------------------------------------------

def test_probe_usa_el_primer_candidato_que_funciona(monkeypatch):
    llamadas = _fake_run(monkeypatch, {
        "models list --json": _Proc(0, json.dumps(["m1", "m2"])),
    })

    r = P.probe_claude_models(cli_bin="claude")

    assert r.ok is True and r.models == ("m1", "m2")
    assert r.command == "models list --json" and r.reason == "ok"
    assert len(llamadas) == 1, "no sigue probando si el primero anduvo"


def test_probe_cae_al_siguiente_candidato(monkeypatch):
    _fake_run(monkeypatch, {
        "models list --json": _Proc(1, ""),
        "models --json": _Proc(0, json.dumps({"models": [{"id": "m9"}]})),
    })

    r = P.probe_claude_models(cli_bin="claude")

    assert r.models == ("m9",) and r.command == "models --json"


def test_probe_nunca_invoca_un_modelo(monkeypatch):
    """Costo de tokens CERO: solo subcomandos de listado, sin prompt."""
    llamadas = _fake_run(monkeypatch, {})

    P.probe_claude_models(cli_bin="claude")

    for sub, kw in llamadas:
        assert "-p" not in sub and "--print" not in sub
        assert "--model" not in sub
        assert kw.get("shell") is False, "sin shell"
        assert kw.get("timeout"), "siempre con timeout"


def test_probe_sin_cli_no_revienta(monkeypatch):
    assert P.probe_claude_models(cli_bin="").reason == "cli_not_found"

    _fake_run(monkeypatch, {"models list --json": FileNotFoundError()})
    assert P.probe_claude_models(cli_bin="claude").reason == "cli_not_found"


def test_probe_timeout_se_reporta(monkeypatch):
    _fake_run(monkeypatch, {
        c: subprocess.TimeoutExpired(cmd="claude", timeout=5)
        for c in ("models list --json", "models --json", "--list-models")
    })

    r = P.probe_claude_models(cli_bin="claude")

    assert r.ok is False and r.reason == "timeout"


def test_probe_json_ilegible_se_reporta(monkeypatch):
    _fake_run(monkeypatch, {"models list --json": _Proc(0, "no soy json")})

    assert P.probe_claude_models(cli_bin="claude").reason == "parse_error"


def test_probe_json_valido_pero_sin_ids(monkeypatch):
    _fake_run(monkeypatch, {"models list --json": _Proc(0, json.dumps({"otra": 1}))})

    assert P.probe_claude_models(cli_bin="claude").reason == "parse_error"


def test_probe_ningun_candidato_anduvo(monkeypatch):
    _fake_run(monkeypatch, {})

    r = P.probe_claude_models(cli_bin="claude")

    assert r.ok is False and r.reason == "no_candidate_worked" and r.models == ()


def test_probe_deduplica_conservando_el_orden(monkeypatch):
    _fake_run(monkeypatch, {"models list --json": _Proc(0, json.dumps(["b", "a", "b"]))})

    assert P.probe_claude_models(cli_bin="claude").models == ("b", "a")


def test_probe_una_excepcion_rara_no_propaga(monkeypatch):
    _fake_run(monkeypatch, {"models list --json": RuntimeError("algo raro")})

    assert P.probe_claude_models(cli_bin="claude").ok is False


# ---------------------------------------------------------------------------
# Merge en el catálogo — UNION, nunca resta
# ---------------------------------------------------------------------------

@pytest.fixture
def catalogo_base() -> dict:
    return {"runtimes": {"claude_code_cli": {
        "source": "static_config_file",
        "models": [{"id": "claude-sonnet-5", "label": "Sonnet 5"}],
        "efforts": [], "effort_support": {},
    }}}


@pytest.fixture
def probe_on(monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_MODEL_PROBE_ENABLED", True, raising=False)
    # El merge se saltea bajo STACKY_TEST_MODE (para que ningún test spawnee el
    # CLI). Acá se prueba el merge en sí, así que se sale de ese modo a propósito
    # y el probe se mockea; nunca se ejecuta un proceso de verdad.
    monkeypatch.delenv("STACKY_TEST_MODE", raising=False)


def _con_probe(monkeypatch, resultado):
    from services import model_catalog

    monkeypatch.setattr("services.model_probe.probe_claude_models",
                        lambda **kw: resultado)
    monkeypatch.setattr("services.claude_code_cli_runner._resolve_claude_code_cli_bin",
                        lambda: "claude")
    return model_catalog


def test_merge_agrega_los_descubiertos(catalogo_base, probe_on, monkeypatch):
    mc = _con_probe(monkeypatch, P.ProbeResult(True, ("modelo-nuevo",), "cmd", "ok"))

    resultado = mc._merge_probe(catalogo_base)

    cli = resultado["runtimes"]["claude_code_cli"]
    ids = [m["id"] for m in cli["models"]]
    assert ids == ["claude-sonnet-5", "modelo-nuevo"], "se agrega AL FINAL"
    assert "detectado en el CLI" in cli["models"][1]["label"]
    assert cli["source"] == "static_config_file+live_probe"
    assert cli["probe"]["added"] == ["modelo-nuevo"]


def test_merge_nunca_resta(catalogo_base, probe_on, monkeypatch):
    """El probe puede ser incompleto: restar rompería una selección vigente."""
    mc = _con_probe(monkeypatch, P.ProbeResult(True, ("otro",), "cmd", "ok"))

    resultado = mc._merge_probe(catalogo_base)

    ids = [m["id"] for m in resultado["runtimes"]["claude_code_cli"]["models"]]
    assert "claude-sonnet-5" in ids


def test_merge_no_duplica_lo_conocido(catalogo_base, probe_on, monkeypatch):
    mc = _con_probe(monkeypatch, P.ProbeResult(True, ("claude-sonnet-5",), "cmd", "ok"))

    resultado = mc._merge_probe(catalogo_base)

    cli = resultado["runtimes"]["claude_code_cli"]
    assert len(cli["models"]) == 1
    assert cli["probe"]["added"] == []
    assert cli["source"] == "static_config_file", "sin altas, la procedencia no cambia"


def test_merge_probe_fallido_deja_el_catalogo_intacto(catalogo_base, probe_on, monkeypatch):
    mc = _con_probe(monkeypatch, P.ProbeResult(False, (), "", "cli_not_found"))

    resultado = mc._merge_probe(catalogo_base)

    cli = resultado["runtimes"]["claude_code_cli"]
    assert len(cli["models"]) == 1
    assert cli["probe"]["reason"] == "cli_not_found", "se dice POR QUÉ no se pudo"


def test_merge_flag_off_no_toca_nada(catalogo_base, monkeypatch):
    from config import config as cfg
    from services import model_catalog

    monkeypatch.setattr(cfg, "STACKY_MODEL_PROBE_ENABLED", False, raising=False)

    resultado = model_catalog._merge_probe(catalogo_base)

    assert "probe" not in resultado["runtimes"]["claude_code_cli"]


def test_merge_no_rompe_con_catalogo_raro(probe_on, monkeypatch):
    from services import model_catalog

    for raro in ({}, {"runtimes": {}}, {"runtimes": {"claude_code_cli": "no soy dict"}}):
        assert model_catalog._merge_probe(dict(raro)) is not None


def test_flag_registrada_default_on():
    from config import config as cfg
    from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    spec = next((s for s in FLAG_REGISTRY if s.key == "STACKY_MODEL_PROBE_ENABLED"), None)
    assert spec is not None and spec.default is True
    assert getattr(cfg, "STACKY_MODEL_PROBE_ENABLED") is True
    assert "STACKY_MODEL_PROBE_ENABLED" in _CURATED_DEFAULTS_ON
    todas = {k for keys in _CATEGORY_KEYS.values() for k in keys}
    assert "STACKY_MODEL_PROBE_ENABLED" in todas


def test_presupuesto_total_acotado(monkeypatch):
    """3 candidatos colgados no pueden sumar 15s bloqueando el catálogo."""
    pedidos: list = []

    def _run(cmd, **kw):
        pedidos.append(kw.get("timeout"))
        raise subprocess.TimeoutExpired(cmd="claude", timeout=kw.get("timeout") or 0)

    monkeypatch.setattr(subprocess, "run", _run)

    r = P.probe_claude_models(cli_bin="claude", timeout_sec=5)

    assert r.reason == "timeout"
    assert len(pedidos) == 1, "tras agotar el presupuesto no se sigue probando"
    assert pedidos[0] <= P._TOTAL_BUDGET_SEC


def test_test_mode_no_spawnea_procesos(monkeypatch, catalogo_base, probe_on):
    """Un test del catálogo no depende de si hay un CLI en la máquina."""
    from services import model_catalog

    monkeypatch.setenv("STACKY_TEST_MODE", "1")

    def _no_llamar(**kw):
        raise AssertionError("no se puede spawnear un proceso bajo pytest")

    monkeypatch.setattr("services.model_probe.probe_claude_models", _no_llamar)

    assert model_catalog._merge_probe(catalogo_base) is catalogo_base
