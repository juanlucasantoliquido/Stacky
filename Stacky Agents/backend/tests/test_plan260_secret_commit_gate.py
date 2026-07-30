"""Plan 260 F5 — ningún camino escribe un YAML con un secreto literal.

Dos motores (audit_yaml: SEC*+OPT*; lint_yaml: PL001..PL014), dos caminos que
escriben YAML (el generador y el editor NL), un solo conjunto congelado por
motor. Filtro SIEMPRE por código, jamás por severidad (las 3 PL de secreto
son SEV_WARNING).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import config

# AUDIT_RULES se puebla de forma PEREZOSA (los imports de cicd_security_rules
# y pipeline_recommendations viven DENTRO de audit_yaml(), no al tope del
# módulo). Importarlos acá dispara los decoradores @audit_rule antes de que
# cualquier test lea el diccionario directamente.
import services.cicd_security_rules  # noqa: F401
import services.pipeline_recommendations  # noqa: F401


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


class _FakeSpec:
    name = "demo"

    def validate(self):
        return []


def _mock_generator_deps(monkeypatch, yaml_text: str):
    import api.pipeline_generator as gen_mod

    monkeypatch.setattr(gen_mod, "dict_to_spec", lambda body: _FakeSpec())
    monkeypatch.setattr(gen_mod, "to_ado_yaml", lambda spec: yaml_text)
    monkeypatch.setattr(gen_mod, "to_gitlab_yaml", lambda spec: yaml_text)


def _mock_writer(monkeypatch) -> MagicMock:
    import api.pipeline_generator as gen_mod

    writer = MagicMock()
    writer.commit_file.return_value = {
        "branch": "feature/x", "commit_sha": "abc123", "web_url": "http://x/commit/abc123",
    }
    monkeypatch.setattr(gen_mod, "get_repo_writer", lambda project=None: writer)
    return writer


def _flags_generator_on(monkeypatch, secret_gate=True):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_GENERATOR_ENABLED", True)
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_SECRET_COMMIT_GATE_ENABLED", secret_gate)


# ── 1 ────────────────────────────────────────────────────────────────────────
def test_f5_cada_codigo_bloqueante_dispara_de_verdad():
    """(ADICIÓN 1, KPI-6) Para CADA código bloqueante, el repro que el propio
    catálogo declara lo produce en el motor que el gate realmente invoca."""
    from services.cicd_audit_core import AUDIT_RULES, audit_yaml
    from services.ci_env_gate import SECRET_BLOCKING_AUDIT, SECRET_BLOCKING_LINT
    from services.pipeline_lint import _RULES, lint_yaml

    for code in SECRET_BLOCKING_AUDIT:
        assert code in AUDIT_RULES, "%s no existe en el motor de audit" % code
        assert AUDIT_RULES[code].repro, "%s sin repro en el catalogo" % code
        prov, yaml_min = AUDIT_RULES[code].repro
        rep = audit_yaml(yaml_min, provider=prov)
        assert any(f.code == code for f in rep.findings), (
            "%s esta declarado bloqueante pero su propio repro no lo dispara" % code)

    repros_lint = {c: r for c, _s, _p, _f, r in _RULES}
    for code in SECRET_BLOCKING_LINT:
        assert repros_lint.get(code), "%s sin repro en el catalogo del linter" % code
        prov, yaml_min = repros_lint[code]
        rep = lint_yaml(yaml_min, prov)
        assert any(f.code == code for f in rep.findings), (
            "%s esta declarado bloqueante pero lint_yaml no lo produce" % code)


# ── 2 ────────────────────────────────────────────────────────────────────────
def test_f5_vocabulario_de_provider(client, monkeypatch):
    """(v2, C2) El string que llega a audit_yaml pertenece a _PROVIDERS."""
    import services.cicd_audit_core as audit_mod
    from api.pipeline_audit import _PROVIDERS
    from services.cicd_security_rules import _REPRO_SEC001

    capturados = []
    original = audit_mod.audit_yaml

    def _espia(yaml_text, *, provider, **kw):
        capturados.append(provider)
        return original(yaml_text, provider=provider, **kw)

    monkeypatch.setattr(audit_mod, "audit_yaml", _espia)
    _flags_generator_on(monkeypatch)
    _mock_generator_deps(monkeypatch, "trigger: main\n")
    _mock_writer(monkeypatch)

    client.post("/api/pipeline-generator/commit", json={
        "name": "demo", "confirm": True, "target": "ado"})
    assert capturados
    for p in capturados:
        assert p in _PROVIDERS, "%r no es del vocabulario de reglas" % p


# ── 3 ────────────────────────────────────────────────────────────────────────
def test_f5_target_basura_no_apaga_reglas(client, monkeypatch):
    """(v3, C7) target=None/"ADO"/"azure_devops" -> el string que llega a
    audit_yaml sigue siendo "ado" o "gitlab", espejando el renderer elegido."""
    import services.cicd_audit_core as audit_mod

    for target_basura in (None, "ADO", "azure_devops"):
        capturados = []
        original = audit_mod.audit_yaml

        def _espia(yaml_text, *, provider, **kw):
            capturados.append(provider)
            return original(yaml_text, provider=provider, **kw)

        monkeypatch.setattr(audit_mod, "audit_yaml", _espia)
        _flags_generator_on(monkeypatch)
        _mock_generator_deps(monkeypatch, "trigger: main\n")
        _mock_writer(monkeypatch)

        client.post("/api/pipeline-generator/commit", json={
            "name": "demo", "confirm": True, "target": target_basura})
        assert capturados, target_basura
        assert capturados[0] in ("ado", "gitlab"), (target_basura, capturados)


# ── 4 ────────────────────────────────────────────────────────────────────────
def test_f5_generator_rechaza_secreto_literal(client, monkeypatch):
    from services.cicd_security_rules import _REPRO_SEC001

    _flags_generator_on(monkeypatch)
    _mock_generator_deps(monkeypatch, _REPRO_SEC001)
    writer = _mock_writer(monkeypatch)

    r = client.post("/api/pipeline-generator/commit", json={
        "name": "demo", "confirm": True, "target": "ado"})
    assert r.status_code == 422
    assert r.get_json()["kind"] == "secret_in_yaml"
    writer.commit_file.assert_not_called()


# ── 5 ────────────────────────────────────────────────────────────────────────
def test_f5_generator_deja_pasar_yaml_limpio(client, monkeypatch):
    _flags_generator_on(monkeypatch)
    _mock_generator_deps(monkeypatch, "trigger: main\nsteps:\n- script: echo hola\n")
    writer = _mock_writer(monkeypatch)

    r = client.post("/api/pipeline-generator/commit", json={
        "name": "demo", "confirm": True, "target": "ado"})
    assert r.status_code == 200
    writer.commit_file.assert_called_once()


# ── 6 ────────────────────────────────────────────────────────────────────────
def test_f5_yaml_no_auditable_no_se_commitea(client, monkeypatch):
    """(v2, C9; ampliado v3, C6) TRES casos: >512KB, no parseable, no-dict."""
    _flags_generator_on(monkeypatch)
    writer = _mock_writer(monkeypatch)

    casos = {
        "demasiado_grande": "a: 1\n#" + ("x" * 600_000),
        "no_parseable": "a: [1, 2\nb: }{\n",
        "no_dict": "- uno\n- dos\n",
    }
    for nombre, yaml_malo in casos.items():
        writer.commit_file.reset_mock()
        _mock_generator_deps(monkeypatch, yaml_malo)
        r = client.post("/api/pipeline-generator/commit", json={
            "name": "demo", "confirm": True, "target": "ado"})
        assert r.status_code == 422, nombre
        assert r.get_json()["kind"] == "secret_gate_indeterminado", nombre
        writer.commit_file.assert_not_called()


# ── 7 ────────────────────────────────────────────────────────────────────────
def test_f5_editor_rechaza_secreto_literal():
    from services.pipeline_diff import GATE_SECRET, review_patch
    from services.pipeline_lint import _RULES

    repro_map = {c: r for c, _s, _p, _f, r in _RULES}
    _prov, yaml_malo = repro_map["PL012"]
    review = review_patch("trigger: main\n", yaml_malo, (), profile="dotnet_framework",
                          secret_gate=True)
    gate_secret = next(g for g in review.gates if g.gate == GATE_SECRET)
    assert gate_secret.passed is False
    assert any(f.code == "PL012" for f in gate_secret.new_errors)
    assert review.ok is False


# ── 8 ────────────────────────────────────────────────────────────────────────
def test_f5_editor_gate_lint_intacto():
    """(v2, C3) El GateDelta de GATE_LINT es idéntico al de antes del cambio
    para un caso sin fuga (backward-compatible)."""
    from services.pipeline_diff import GATE_LINT, review_patch

    before = "trigger: main\n"
    after = "trigger: main\nresources: {}\n"
    review = review_patch(before, after, (), profile="dotnet_framework", secret_gate=True)
    gate_lint = next(g for g in review.gates if g.gate == GATE_LINT)
    assert gate_lint.passed is True
    assert gate_lint.new_errors == ()


# ── 9 ────────────────────────────────────────────────────────────────────────
def test_f5_pipeline_diff_sigue_puro():
    import inspect
    from pathlib import Path

    from services.pipeline_diff import review_patch

    src = (Path(__file__).resolve().parent.parent / "services" / "pipeline_diff.py").read_text(
        encoding="utf-8")
    assert "config" not in src, "pipeline_diff.py debe seguir PURO: 0 referencias a config"

    firma = inspect.signature(review_patch)
    assert firma.parameters["secret_gate"].default is True


# ── 10 ───────────────────────────────────────────────────────────────────────
def test_f5_pl013_no_bloquea():
    """Control negativo: PL013 SI existe y SI puede disparar (con
    known_variables no-None), pero esta explicitamente excluido del conjunto
    bloqueante — bloquear con PL013 volveria incommiteable media pipeline
    legitima que simplemente no mando la caja fuerte."""
    from services.ci_env_gate import SECRET_BLOCKING_LINT
    from services.pipeline_lint import _RULES, lint_yaml

    repro_map = {c: r for c, _s, _p, _f, r in _RULES}
    prov, yaml_min = repro_map["PL013"]
    rep = lint_yaml(yaml_min, prov, known_variables=[])
    assert any(f.code == "PL013" for f in rep.findings), "el repro no dispara PL013"
    assert "PL013" not in SECRET_BLOCKING_LINT


# ── 11 ───────────────────────────────────────────────────────────────────────
def test_f5_el_gate_corre_antes_del_masking():
    """Se audita el texto CRUDO. El módulo no debe enmascarar antes de
    auditar: si lo hiciera, SEC001 dejaría de ver el secreto."""
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent / "services" / "ci_env_gate.py").read_text(
        encoding="utf-8")
    assert "mask_token_values" not in src

    from services.cicd_audit_core import AUDIT_RULES
    from services.ci_env_gate import evaluar_gate_secretos

    prov, yaml_min = AUDIT_RULES["SEC001"].repro
    duros, auditado = evaluar_gate_secretos(yaml_min, provider=prov)
    assert auditado
    assert any(c == "SEC001" for c, _l, _m in duros)


# ── 12 ───────────────────────────────────────────────────────────────────────
def test_f5_el_mensaje_de_error_no_trae_el_secreto(client, monkeypatch):
    from services.cicd_security_rules import _REPRO_SEC001

    _flags_generator_on(monkeypatch)
    _mock_generator_deps(monkeypatch, _REPRO_SEC001)
    _mock_writer(monkeypatch)

    r = client.post("/api/pipeline-generator/commit", json={
        "name": "demo", "confirm": True, "target": "ado"})
    cuerpo = r.get_data(as_text=True)
    assert "ghp_0123456789abcdefghijklmnopqrstuvwx" not in cuerpo
    data = r.get_json()
    for f in data.get("findings", []):
        assert set(f.keys()) == {"code", "location", "message"}


# ── 13a ──────────────────────────────────────────────────────────────────────
def test_f5_flag_off_no_bloquea_generador(client, monkeypatch):
    from services.cicd_security_rules import _REPRO_SEC001

    _flags_generator_on(monkeypatch, secret_gate=False)
    _mock_generator_deps(monkeypatch, _REPRO_SEC001)
    writer = _mock_writer(monkeypatch)

    r = client.post("/api/pipeline-generator/commit", json={
        "name": "demo", "confirm": True, "target": "ado"})
    assert r.status_code == 200
    writer.commit_file.assert_called_once()


# ── 13b ──────────────────────────────────────────────────────────────────────
def test_f5_flag_off_no_bloquea_editor():
    from services.pipeline_diff import GATE_SECRET, review_patch
    from services.pipeline_lint import _RULES

    repro_map = {c: r for c, _s, _p, _f, r in _RULES}
    _prov, yaml_malo = repro_map["PL012"]
    review = review_patch("trigger: main\n", yaml_malo, (), profile="dotnet_framework",
                          secret_gate=False)
    gate_secret = next(g for g in review.gates if g.gate == GATE_SECRET)
    assert gate_secret.passed is True
    assert gate_secret.new_errors == ()


# ── 14 ───────────────────────────────────────────────────────────────────────
def test_f5_conjuntos_bloqueantes_son_cerrados():
    from services.ci_env_gate import SECRET_BLOCKING_AUDIT, SECRET_BLOCKING_LINT

    assert SECRET_BLOCKING_AUDIT == ("SEC001",)
    assert SECRET_BLOCKING_LINT == ("PL012", "PL014")
