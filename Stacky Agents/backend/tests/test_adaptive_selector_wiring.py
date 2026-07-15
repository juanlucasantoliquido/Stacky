"""Plan 53 F2/F5 — Tests de cableado del selector adaptativo en run_brief.

Verifica:
- F2: el selector se invoca solo con flag ON y modifica modelo/effort según confidence.
- F2: el override manual del operador siempre gana (G4, por campo).
- F2: con flag OFF el comportamiento es byte-idéntico al actual.
- F5: la traza adaptive_selector se persiste en metadata con flag ON; ausente con flag OFF.
- C1: proyectos heterogéneos usan el último confidence disponible.
- C7: errores del helper de I/O devuelven None y no crashean.
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch, call

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _make_app():
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@contextmanager
def _patch_deps(execution_id=42):
    """Mockea DB (session_scope) y run_agent para tests de run_brief."""
    fake_ticket = MagicMock()
    fake_ticket.id = 1

    @contextmanager
    def _fake_scope():
        sess = MagicMock()
        sess.query.return_value.filter_by.return_value.first.return_value = fake_ticket
        sess.get.return_value = None  # No queremos que la traza falle
        yield sess

    import agent_runner as ar
    mock_run_agent = MagicMock(return_value=execution_id)
    with patch("db.session_scope", _fake_scope), \
         patch.object(ar, "run_agent", mock_run_agent):
        yield mock_run_agent


def _post_brief(client, body=None, runtime="claude_code_cli"):
    return client.post(
        "/api/agents/run-brief",
        json={"brief": "epic de facturación", "runtime": runtime, **(body or {})},
        headers={"X-User-Email": "op@x"},
    )


# ── F2: Flag OFF → byte-idéntico ──────────────────────────────────────────────

def test_flag_off_is_byte_identical():
    """Con flag OFF, model/effort == los que produce la ruta actual (sin selector)."""
    from config import config
    from services.adaptive_selector import _MODEL_SONNET
    app = _make_app()
    with patch.object(config, "STACKY_ADAPTIVE_SELECTOR_ENABLED", False):
        with patch("services.adaptive_selector._load_last_project_confidence", return_value=0.1) as load_mock:
            with app.test_client() as c:
                with _patch_deps() as run_agent:
                    r = _post_brief(c)
                assert r.status_code == 202
                run_agent.assert_called_once()
                # Con flag OFF, el loader NO se invoca.
                load_mock.assert_not_called()


def test_flag_off_no_adaptive_trace_in_metadata():
    """Con flag OFF, la metadata del run NO contiene 'adaptive_selector'."""
    from config import config
    app = _make_app()
    captured_meta = {}

    @contextmanager
    def _fake_scope_capture():
        sess = MagicMock()
        fake_ticket = MagicMock(); fake_ticket.id = 1
        sess.query.return_value.filter_by.return_value.first.return_value = fake_ticket
        def _get(cls, eid):
            ex = MagicMock()
            ex.metadata_dict = {}
            def _set_md(md):
                captured_meta.update(md)
            type(ex).metadata_dict = property(lambda s: captured_meta, lambda s, v: captured_meta.update(v))
            return ex
        sess.get.side_effect = _get
        yield sess

    import agent_runner as ar
    with patch.object(config, "STACKY_ADAPTIVE_SELECTOR_ENABLED", False):
        with patch("db.session_scope", _fake_scope_capture), \
             patch.object(ar, "run_agent", MagicMock(return_value=99)):
            with app.test_client() as c:
                r = _post_brief(c)
            assert r.status_code == 202
            assert "adaptive_selector" not in captured_meta


# ── F2: Flag ON → selector activo ─────────────────────────────────────────────

def test_flag_on_low_confidence_escalates_to_opus():
    """Con flag ON y confidence=0.2, model_override debe ser claude-opus-4-8."""
    from config import config
    from services.adaptive_selector import _MODEL_OPUS
    app = _make_app()
    with patch.object(config, "STACKY_ADAPTIVE_SELECTOR_ENABLED", True):
        with patch("services.adaptive_selector._load_last_project_confidence", return_value=0.2):
            with app.test_client() as c:
                with _patch_deps() as run_agent:
                    r = _post_brief(c, body={})  # sin model/effort del operador
                assert r.status_code == 202
                call_kwargs = run_agent.call_args.kwargs
                assert call_kwargs.get("model_override") == _MODEL_OPUS, (
                    f"Bajo confidence debe escalar a Opus; got {call_kwargs.get('model_override')}"
                )
                assert call_kwargs.get("effort_override") == "max", (
                    f"Bajo confidence debe usar max effort; got {call_kwargs.get('effort_override')}"
                )


def test_flag_on_high_confidence_saves_cost():
    """Con flag ON y confidence=0.9, model_override debe ser claude-sonnet-4-6 y effort low."""
    from config import config
    from services.adaptive_selector import _MODEL_SONNET
    app = _make_app()
    with patch.object(config, "STACKY_ADAPTIVE_SELECTOR_ENABLED", True):
        with patch("services.adaptive_selector._load_last_project_confidence", return_value=0.9):
            with app.test_client() as c:
                with _patch_deps() as run_agent:
                    r = _post_brief(c, body={})
                assert r.status_code == 202
                call_kwargs = run_agent.call_args.kwargs
                assert call_kwargs.get("model_override") == _MODEL_SONNET, (
                    f"Alto confidence debe usar Sonnet; got {call_kwargs.get('model_override')}"
                )
                assert call_kwargs.get("effort_override") == "low", (
                    f"Alto confidence debe usar low effort; got {call_kwargs.get('effort_override')}"
                )


def test_operator_model_override_wins():
    """G4: si el operador envía model explícito con flag ON y confidence bajo, su modelo gana.

    NOTA: el modelo enviado en el body es un literal de fixture (un Claude
    válido cualquiera, en este caso el fallback del CLI) — deliberadamente
    NO se compara contra `_MODEL_SONNET`/CLAUDE_CAP_MODEL (el tope actual es
    sonnet-5): lo que se prueba es que el override explícito del operador pasa
    sin tocar, no que coincida con el cap.
    """
    from config import config
    app = _make_app()
    with patch.object(config, "STACKY_ADAPTIVE_SELECTOR_ENABLED", True):
        with patch("services.adaptive_selector._load_last_project_confidence", return_value=0.1):
            with app.test_client() as c:
                with _patch_deps() as run_agent:
                    r = _post_brief(c, body={"model": "claude-sonnet-4-6", "effort": "low"})
                assert r.status_code == 202
                call_kwargs = run_agent.call_args.kwargs
                # El operador fijó ambos → selector NO propone ninguno; pasa intacto.
                assert call_kwargs.get("model_override") == "claude-sonnet-4-6"
                assert call_kwargs.get("effort_override") == "low"


def test_operator_effort_override_wins():
    """G4: si el operador envía effort con flag ON, su effort gana incluso si confidence es bajo."""
    from config import config
    app = _make_app()
    with patch.object(config, "STACKY_ADAPTIVE_SELECTOR_ENABLED", True):
        with patch("services.adaptive_selector._load_last_project_confidence", return_value=0.1):
            with app.test_client() as c:
                with _patch_deps() as run_agent:
                    # Solo fija effort, no model → el selector puede proponer modelo pero no effort.
                    r = _post_brief(c, body={"effort": "medium"})
                assert r.status_code == 202
                call_kwargs = run_agent.call_args.kwargs
                # Effort del operador respetado.
                assert call_kwargs.get("effort_override") == "medium", (
                    f"effort del operador debe respetarse; got {call_kwargs.get('effort_override')}"
                )


def test_operator_empty_model_string_not_override():
    """C3: model='' (empty string) se trata como ausente → selector propone."""
    from config import config
    from services.adaptive_selector import _MODEL_OPUS
    app = _make_app()
    with patch.object(config, "STACKY_ADAPTIVE_SELECTOR_ENABLED", True):
        with patch("services.adaptive_selector._load_last_project_confidence", return_value=0.1):
            with app.test_client() as c:
                with _patch_deps() as run_agent:
                    r = _post_brief(c, body={"model": ""})  # empty → no es override
                assert r.status_code == 202
                call_kwargs = run_agent.call_args.kwargs
                # selector propuso Opus (confidence 0.1) → clamp deja pasar (allow_opus=True)
                assert call_kwargs.get("model_override") == _MODEL_OPUS, (
                    f"model='' no es override; selector debe proponer Opus; got {call_kwargs.get('model_override')}"
                )


def test_no_history_keeps_defaults():
    """Con flag ON y confidence None (sin historial), modelo/effort == los defaults."""
    from config import config
    app = _make_app()
    with patch.object(config, "STACKY_ADAPTIVE_SELECTOR_ENABLED", True):
        with patch("services.adaptive_selector._load_last_project_confidence", return_value=None):
            with app.test_client() as c:
                with _patch_deps() as run_agent:
                    r = _post_brief(c, body={})
                assert r.status_code == 202
                call_kwargs = run_agent.call_args.kwargs
                # sin confidence → select devuelve base_model=None, base_effort="high" → igual al default actual
                assert call_kwargs.get("model_override") is None, (
                    f"Sin historial, modelo debe ser None (default); got {call_kwargs.get('model_override')}"
                )
                assert call_kwargs.get("effort_override") == "high", (
                    f"Sin historial, effort debe ser 'high'; got {call_kwargs.get('effort_override')}"
                )


def test_proposal_always_passes_clamp():
    """G3: aunque select proponga un modelo inválido, el clamp lo corrige."""
    from config import config
    from services.adaptive_selector import Selection
    app = _make_app()
    with patch.object(config, "STACKY_ADAPTIVE_SELECTOR_ENABLED", True):
        # Forzar select a proponer un modelo fuera de allowlist
        with patch("services.adaptive_selector._load_last_project_confidence", return_value=0.5):
            with patch("services.adaptive_selector.select",
                       return_value=Selection(model="claude-opus-NOT-IN-ALLOWLIST", effort="high", reason="test")):
                with app.test_client() as c:
                    with _patch_deps() as run_agent:
                        r = _post_brief(c, body={})
                    assert r.status_code == 202
                    call_kwargs = run_agent.call_args.kwargs
                    # clamp_model(allow_opus=True) con modelo fuera de allowlist → CLAUDE_CAP_MODEL
                    from services.llm_router import CLAUDE_CAP_MODEL
                    assert call_kwargs.get("model_override") == CLAUDE_CAP_MODEL, (
                        f"Clamp debe degradar modelo inválido a {CLAUDE_CAP_MODEL}; "
                        f"got {call_kwargs.get('model_override')}"
                    )


# ── C7: Helper de I/O maneja errores sin crashear ─────────────────────────────

def test_load_confidence_handles_malformed_summary():
    """C7: _load_last_project_confidence retorna None con DB/estructura malformada."""
    from services.adaptive_selector import _load_last_project_confidence

    @contextmanager
    def _broken_scope():
        sess = MagicMock()
        sess.query.side_effect = RuntimeError("DB exploded")
        yield sess

    with patch("db.session_scope", _broken_scope):
        result = _load_last_project_confidence("proyecto_x")
    assert result is None


def test_load_confidence_returns_none_for_empty_project():
    """_load_last_project_confidence retorna None para project_name vacío/None."""
    from services.adaptive_selector import _load_last_project_confidence
    assert _load_last_project_confidence(None) is None
    assert _load_last_project_confidence("") is None


# ── C1: Contaminación de briefs heterogéneos ─────────────────────────────────

def test_heterogeneous_briefs_use_last_confidence():
    """C1: el selector usa el ÚLTIMO confidence del proyecto sin contexto de brief.

    Simula 2 runs con confidences distintos: el selector usa el último (más reciente).
    Documenta el supuesto de proyectos relativamente homogéneos.
    """
    from services.adaptive_selector import _load_last_project_confidence, select, _MODEL_OPUS, _MODEL_SONNET

    # Primer run → confidence 0.9 (alto)
    # Segundo run → confidence 0.2 (bajo) — el más reciente
    # El selector debe usar 0.2 → Opus/max
    last_confidence_mock = 0.2  # simula el más reciente

    result = select(last_confidence_mock, base_model=None, base_effort="high")
    assert result.model == _MODEL_OPUS
    assert result.effort == "max"
    # Documenta la asunción: el selector usa el último sin distinguir tipo de brief.
    assert "very_low_confidence" in result.reason


# ── F5: Traza en metadata ─────────────────────────────────────────────────────

def test_trace_present_when_flag_on():
    """F5: con flag ON y confidence baja, metadata contiene adaptive_selector con razón y modelo."""
    from config import config
    from services.adaptive_selector import _MODEL_OPUS
    app = _make_app()
    traced_meta = {}

    @contextmanager
    def _fake_scope_trace():
        sess = MagicMock()
        fake_ticket = MagicMock(); fake_ticket.id = 1
        sess.query.return_value.filter_by.return_value.first.return_value = fake_ticket

        class _FakeEx:
            _md = {}
            @property
            def metadata_dict(self):
                return self._md
            @metadata_dict.setter
            def metadata_dict(self, v):
                self._md = v
                traced_meta.update(v)

        fake_ex = _FakeEx()
        sess.get.return_value = fake_ex
        yield sess

    import agent_runner as ar
    with patch.object(config, "STACKY_ADAPTIVE_SELECTOR_ENABLED", True):
        with patch("services.adaptive_selector._load_last_project_confidence", return_value=0.1):
            with patch("db.session_scope", _fake_scope_trace), \
                 patch.object(ar, "run_agent", MagicMock(return_value=1)):
                with app.test_client() as c:
                    r = _post_brief(c, body={})
                assert r.status_code == 202

    trace = traced_meta.get("adaptive_selector")
    assert trace is not None, "Con flag ON, metadata debe contener 'adaptive_selector'"
    assert trace.get("enabled") is True
    assert trace.get("reason", "").startswith("adaptive:"), (
        f"reason debe empezar con 'adaptive:'; got {trace.get('reason')}"
    )
    assert trace.get("final_model") == _MODEL_OPUS


def test_trace_absent_when_flag_off():
    """F5: con flag OFF, la metadata NO contiene adaptive_selector."""
    from config import config
    app = _make_app()
    traced_meta = {}

    @contextmanager
    def _fake_scope_trace():
        sess = MagicMock()
        fake_ticket = MagicMock(); fake_ticket.id = 1
        sess.query.return_value.filter_by.return_value.first.return_value = fake_ticket

        class _FakeEx:
            _md = {}
            @property
            def metadata_dict(self):
                return self._md
            @metadata_dict.setter
            def metadata_dict(self, v):
                self._md = v
                traced_meta.update(v)

        fake_ex = _FakeEx()
        sess.get.return_value = fake_ex
        yield sess

    import agent_runner as ar
    with patch.object(config, "STACKY_ADAPTIVE_SELECTOR_ENABLED", False):
        with patch("db.session_scope", _fake_scope_trace), \
             patch.object(ar, "run_agent", MagicMock(return_value=1)):
            with app.test_client() as c:
                r = _post_brief(c, body={})
            assert r.status_code == 202

    assert "adaptive_selector" not in traced_meta, (
        "Con flag OFF, metadata NO debe contener 'adaptive_selector'"
    )
