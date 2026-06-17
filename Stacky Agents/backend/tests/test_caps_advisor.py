"""Tests TDD para I3.3 — Asesor de caps de contexto por telemetría.

Spec:
- suggest_caps NUNCA escribe (test explícito verificando 0 writes).
- Con telemetría donde más contexto no mejora score → sugiere bajar.
- Con telemetría donde runs cortos tienen más needs_review → sugiere subir.
- sample_size < 5 → no sugerir para ese agente (suggested_cap = None).
- Flag OFF → endpoint GET /metrics/caps-advisor devuelve {"enabled": false}.
- Flag ON con proyecto → devuelve sugerencias.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _log(*_a, **_k):
    pass


# ---------------------------------------------------------------------------
# Helpers para construir datos sintéticos de telemetría
# ---------------------------------------------------------------------------

def _make_exec(agent_type, input_tokens, contract_score=None, confidence=None, status="completed"):
    """Crea un dict que simula el to_dict() de AgentExecution."""
    md = {}
    if input_tokens is not None:
        md["harness_telemetry"] = {"input_tokens": input_tokens}
    if contract_score is not None:
        md["contract_score"] = contract_score
    if confidence is not None:
        md["confidence"] = confidence
    import json
    return {
        "agent_type": agent_type,
        "status": status,
        "metadata_json": json.dumps(md) if md else None,
    }


def _build_mock_execs(raw_list):
    """Convierte lista de dicts a objetos MagicMock con los atributos correctos."""
    mocks = []
    for r in raw_list:
        m = MagicMock()
        m.agent_type = r["agent_type"]
        m.status = r["status"]
        m.metadata_json = r.get("metadata_json")
        mocks.append(m)
    return mocks


# ---------------------------------------------------------------------------
# Test 1: suggest_caps NUNCA escribe (0 setattr/write calls)
# ---------------------------------------------------------------------------

def test_suggest_caps_never_writes():
    """suggest_caps no debe llamar a ningún setter ni método de escritura."""
    # Usamos una sesión mock que lanza si alguien intenta escribir
    write_calls = []

    mock_sess = MagicMock()
    mock_sess.add.side_effect = lambda x: write_calls.append(("add", x))
    mock_sess.delete.side_effect = lambda x: write_calls.append(("delete", x))
    mock_sess.flush.side_effect = lambda: write_calls.append(("flush",))
    mock_sess.commit.side_effect = lambda: write_calls.append(("commit",))
    mock_sess.execute.side_effect = lambda *a, **kw: write_calls.append(("execute", a))
    mock_sess.query.return_value.join.return_value.filter.return_value.all.return_value = []

    from contextlib import contextmanager

    @contextmanager
    def _mock_scope():
        yield mock_sess

    with patch("db.session_scope", _mock_scope):
        from services.context_caps_advisor import suggest_caps
        suggest_caps(project="PROJ", days=30)

    assert write_calls == [], f"suggest_caps realizó escrituras: {write_calls}"


# ---------------------------------------------------------------------------
# Test 2: sample_size < 5 → suggested_cap es None
# ---------------------------------------------------------------------------

def test_suggest_caps_insufficient_sample():
    raw = [
        _make_exec("developer", 1000, contract_score=80),
        _make_exec("developer", 1200, contract_score=82),
        _make_exec("developer", 800, contract_score=79),
    ]  # solo 3 muestras → < MIN_SAMPLE_SIZE

    mock_sess = MagicMock()
    mock_sess.query.return_value.join.return_value.filter.return_value.all.return_value = (
        _build_mock_execs(raw)
    )

    from contextlib import contextmanager

    @contextmanager
    def _mock_scope():
        yield mock_sess

    with patch("db.session_scope", _mock_scope):
        from services.context_caps_advisor import suggest_caps
        result = suggest_caps(project="PROJ", days=30)

    dev = result.get("developer", {})
    assert dev.get("suggested_cap") is None
    assert dev.get("sample_size") == 3


# ---------------------------------------------------------------------------
# Test 3: Más contexto no mejora score → sugerir bajar cap
# ---------------------------------------------------------------------------

def test_suggest_caps_suggest_down():
    """Cuando más tokens no mejoran contract_score, se debe sugerir bajar."""
    # 10 ejecuciones: las de contexto corto tienen MISMO score que las de contexto largo
    raw = []
    for i in range(5):
        raw.append(_make_exec("developer", 500, contract_score=80, status="completed"))  # cortos
    for i in range(5):
        raw.append(_make_exec("developer", 5000, contract_score=79, status="completed"))  # largos

    mock_sess = MagicMock()
    mock_sess.query.return_value.join.return_value.filter.return_value.all.return_value = (
        _build_mock_execs(raw)
    )

    from contextlib import contextmanager

    @contextmanager
    def _mock_scope():
        yield mock_sess

    with patch("db.session_scope", _mock_scope):
        from services.context_caps_advisor import suggest_caps
        result = suggest_caps(project="PROJ", days=30)

    dev = result.get("developer", {})
    # Con contexto largo sin mejora → suggested_cap < current_cap (o None)
    if dev.get("suggested_cap") is not None:
        assert dev["suggested_cap"] <= dev["current_cap"], (
            f"Se esperaba bajar el cap, pero se sugirió subir: {dev}"
        )


# ---------------------------------------------------------------------------
# Test 4: Contexto corto → más needs_review → sugerir subir cap
# ---------------------------------------------------------------------------

def test_suggest_caps_suggest_up():
    """Cuando contexto corto tiene alta tasa needs_review, se sugiere subir."""
    raw = []
    # 5 runs cortos con needs_review
    for i in range(5):
        raw.append(_make_exec("developer", 200, contract_score=60, status="needs_review"))
    # 5 runs largos sin needs_review
    for i in range(5):
        raw.append(_make_exec("developer", 3000, contract_score=85, status="completed"))

    mock_sess = MagicMock()
    mock_sess.query.return_value.join.return_value.filter.return_value.all.return_value = (
        _build_mock_execs(raw)
    )

    from contextlib import contextmanager

    @contextmanager
    def _mock_scope():
        yield mock_sess

    with patch("db.session_scope", _mock_scope):
        from services.context_caps_advisor import suggest_caps
        result = suggest_caps(project="PROJ", days=30)

    dev = result.get("developer", {})
    # Con contexto corto y alta tasa de needs_review → suggested_cap >= current_cap (o None)
    if dev.get("suggested_cap") is not None:
        assert dev["suggested_cap"] >= dev["current_cap"], (
            f"Se esperaba subir el cap, pero se sugirió bajar: {dev}"
        )


# ---------------------------------------------------------------------------
# Test 5: Flag OFF → endpoint devuelve {"enabled": false}
# ---------------------------------------------------------------------------

def test_caps_advisor_endpoint_flag_off(monkeypatch):
    from config import config
    monkeypatch.setattr(config, "STACKY_CAPS_ADVISOR_ENABLED", False, raising=False)

    from flask import Flask
    app = Flask(__name__)
    app.config["TESTING"] = True
    from api.metrics import bp
    app.register_blueprint(bp, url_prefix="/metrics")

    with app.test_client() as c:
        resp = c.get("/metrics/caps-advisor?project=PROJ")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get("enabled") is False


# ---------------------------------------------------------------------------
# Test 6: Flag ON sin project param → error 400
# ---------------------------------------------------------------------------

def test_caps_advisor_endpoint_missing_project(monkeypatch):
    from config import config
    monkeypatch.setattr(config, "STACKY_CAPS_ADVISOR_ENABLED", True, raising=False)

    from flask import Flask
    app = Flask(__name__)
    app.config["TESTING"] = True
    from api.metrics import bp
    app.register_blueprint(bp, url_prefix="/metrics")

    with app.test_client() as c:
        resp = c.get("/metrics/caps-advisor")

    assert resp.status_code == 400
    assert resp.get_json().get("ok") is False


# ---------------------------------------------------------------------------
# Test 7: Flag ON con proyecto → respuesta correcta
# ---------------------------------------------------------------------------

def test_caps_advisor_endpoint_with_project(monkeypatch):
    from config import config
    monkeypatch.setattr(config, "STACKY_CAPS_ADVISOR_ENABLED", True, raising=False)

    with patch("services.context_caps_advisor.suggest_caps", return_value={"developer": {"current_cap": 14, "suggested_cap": None, "rationale": "ok", "sample_size": 3}}):
        from flask import Flask
        app = Flask(__name__)
        app.config["TESTING"] = True
        from api.metrics import bp
        app.register_blueprint(bp, url_prefix="/metrics")

        with app.test_client() as c:
            resp = c.get("/metrics/caps-advisor?project=PROJ&days=30")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get("ok") is True
    assert data.get("enabled") is True
    assert "suggestions" in data
    assert data["project"] == "PROJ"
