"""Plan 77 F2 — Helper publish_issue_phase_from_run.

Verifica: noop en varios caminos, posteo correcto, idempotencia visible
(phase_already_present), paridad GitLab, no-fatal, y fallback de output crudo.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture()
def _app_ctx():
    from app import create_app
    app = create_app()
    with app.app_context():
        yield app


def _make_issue_ticket(ado_id: int, project_name: str = "Pacifico"):
    """Persiste un Ticket Issue en la DB de test y lo devuelve."""
    from api.tickets import _persist_issue_ticket
    _persist_issue_ticket(
        ado_id=ado_id,
        title=f"Issue {ado_id}",
        description_html="<h1>Issue test</h1>",
        url=f"http://ado/{ado_id}",
        project_name=project_name,
    )


def _make_epic_ticket(ado_id: int):
    """Persiste un Ticket tipo Epic."""
    from db import session_scope
    from models import Ticket
    with session_scope() as session:
        t = Ticket()
        t.ado_id = ado_id
        t.title = f"Epic {ado_id}"
        t.work_item_type = "Epic"
        t.project = "Pacifico"
        t.stacky_project_name = "Pacifico"
        session.add(t)


def _fake_ado_client(comment_exists_return: bool = False) -> MagicMock:
    """Fake AdoClient: sin atributo `name` → rama legacy."""
    fake = MagicMock()
    fake.comment_exists.return_value = comment_exists_return
    del fake.name  # Asegurar que no tiene `name` como string
    return fake


def _fake_provider(comment_exists_return: bool = False) -> MagicMock:
    """Fake TrackerProvider: con atributo `name` (string) → rama provider."""
    fake = MagicMock()
    fake.name = "gitlab"  # string → is_provider = True
    fake.comment_exists.return_value = comment_exists_return
    return fake


# ---------------------------------------------------------------------------
# Casos de test
# ---------------------------------------------------------------------------

def test_noop_when_flag_off(_app_ctx):
    """[C1] Con flag OFF, publish_issue_phase_from_run retorna None sin llamar post_comment."""
    from api.tickets import publish_issue_phase_from_run
    _make_issue_ticket(ado_id=9110)
    fake = _fake_ado_client()

    with patch("api.tickets._provider_for_ticket", return_value=None), \
         patch("api.tickets._ado_client_for_ticket", return_value=fake), \
         patch("config.config.STACKY_ISSUE_PHASE_COMMENTS_ENABLED", False):
        result = publish_issue_phase_from_run(
            ticket_id=9999,  # no importa — el flag está OFF
            agent_type="technical",
            output="<h1>análisis</h1>",
            project_name="Pacifico",
        )
    assert result is None
    fake.post_comment.assert_not_called()


def test_noop_when_agent_not_a_phase(_app_ctx):
    """Con flag ON, agent_type=business → None (business crea el WI, no posta fase)."""
    from api.tickets import publish_issue_phase_from_run
    _make_issue_ticket(ado_id=9111)
    fake = _fake_ado_client()

    with patch("api.tickets._provider_for_ticket", return_value=None), \
         patch("api.tickets._ado_client_for_ticket", return_value=fake), \
         patch("config.config.STACKY_ISSUE_PHASE_COMMENTS_ENABLED", True):
        result = publish_issue_phase_from_run(
            ticket_id=9111,
            agent_type="business",
            output="<h1>algo</h1>",
            project_name="Pacifico",
        )
    assert result is None
    fake.post_comment.assert_not_called()


def test_noop_when_ticket_not_issue(_app_ctx):
    """Flag ON, ticket Epic → None (solo actúa sobre Issues)."""
    from api.tickets import publish_issue_phase_from_run
    _make_epic_ticket(ado_id=9112)
    # Necesitamos el ticket_id de la Ticket, no el ado_id
    from db import session_scope
    from models import Ticket
    with session_scope() as session:
        t = session.query(Ticket).filter(Ticket.ado_id == 9112).first()
        tid = t.id

    fake = _fake_ado_client()
    with patch("api.tickets._provider_for_ticket", return_value=None), \
         patch("api.tickets._ado_client_for_ticket", return_value=fake), \
         patch("config.config.STACKY_ISSUE_PHASE_COMMENTS_ENABLED", True):
        result = publish_issue_phase_from_run(
            ticket_id=tid,
            agent_type="technical",
            output="<h1>análisis</h1>",
            project_name="Pacifico",
        )
    assert result is None
    fake.post_comment.assert_not_called()


def test_posts_tecnico_comment_for_technical_agent(_app_ctx):
    """Flag ON, ticket Issue con ado_id=9113, agent_type=technical → posta comentario de fase tecnico."""
    from api.tickets import publish_issue_phase_from_run, _ISSUE_PHASE_MARKERS
    _make_issue_ticket(ado_id=9113)
    from db import session_scope
    from models import Ticket
    with session_scope() as session:
        t = session.query(Ticket).filter(Ticket.ado_id == 9113).first()
        tid = t.id

    fake = _fake_ado_client(comment_exists_return=False)
    with patch("api.tickets._provider_for_ticket", return_value=None), \
         patch("api.tickets._ado_client_for_ticket", return_value=fake), \
         patch("config.config.STACKY_ISSUE_PHASE_COMMENTS_ENABLED", True):
        result = publish_issue_phase_from_run(
            ticket_id=tid,
            agent_type="technical",
            output="<h1>análisis técnico</h1>",
            project_name="Pacifico",
        )
    assert result is not None
    assert result["phase"] == "tecnico"
    assert result["posted"] is True
    assert result["ado_id"] == 9113
    # Verificar que post_comment fue llamado exactamente una vez
    assert fake.post_comment.call_count == 1
    # Verificar que el texto del comentario contiene el marker de tecnico
    call_args = fake.post_comment.call_args
    comment_text = call_args[0][1] if call_args[0] else call_args[1].get("body", "")
    # AdoClient legacy: post_comment(ado_id, marked_html, fmt="html")
    posted_content = str(fake.post_comment.call_args)
    assert _ISSUE_PHASE_MARKERS["tecnico"] in posted_content or \
           (fake.post_comment.call_args[0] and
            _ISSUE_PHASE_MARKERS["tecnico"] in str(fake.post_comment.call_args[0]))


def test_posts_implementacion_for_developer_agent(_app_ctx):
    """Flag ON, ticket Issue, agent_type=developer → marker implementacion."""
    from api.tickets import publish_issue_phase_from_run, _ISSUE_PHASE_MARKERS
    _make_issue_ticket(ado_id=9114)
    from db import session_scope
    from models import Ticket
    with session_scope() as session:
        t = session.query(Ticket).filter(Ticket.ado_id == 9114).first()
        tid = t.id

    fake = _fake_ado_client(comment_exists_return=False)
    with patch("api.tickets._provider_for_ticket", return_value=None), \
         patch("api.tickets._ado_client_for_ticket", return_value=fake), \
         patch("config.config.STACKY_ISSUE_PHASE_COMMENTS_ENABLED", True):
        result = publish_issue_phase_from_run(
            ticket_id=tid,
            agent_type="developer",
            output="<h1>implementación</h1>",
            project_name="Pacifico",
        )
    assert result is not None
    assert result["phase"] == "implementacion"
    assert result["posted"] is True
    posted_content = str(fake.post_comment.call_args)
    assert _ISSUE_PHASE_MARKERS["implementacion"] in posted_content


def test_phase_already_present_returns_not_posted(_app_ctx):
    """[ADICIÓN C6] Si comment_exists devuelve True, post_comment NO se llama; retorno posted=False reason=phase_already_present."""
    from api.tickets import publish_issue_phase_from_run
    _make_issue_ticket(ado_id=9115)
    from db import session_scope
    from models import Ticket
    with session_scope() as session:
        t = session.query(Ticket).filter(Ticket.ado_id == 9115).first()
        tid = t.id

    # Fake que indica que el comentario YA existe
    fake = _fake_ado_client(comment_exists_return=True)
    with patch("api.tickets._provider_for_ticket", return_value=None), \
         patch("api.tickets._ado_client_for_ticket", return_value=fake), \
         patch("config.config.STACKY_ISSUE_PHASE_COMMENTS_ENABLED", True):
        result = publish_issue_phase_from_run(
            ticket_id=tid,
            agent_type="technical",
            output="<h1>ya publicado</h1>",
            project_name="Pacifico",
        )
    assert result is not None
    assert result["posted"] is False
    assert result["reason"] == "phase_already_present"
    assert result["ado_id"] == 9115
    fake.post_comment.assert_not_called()


def test_empty_output_returns_not_posted(_app_ctx):
    """Output vacío → posted=False reason=empty_output, sin llamar post_comment."""
    from api.tickets import publish_issue_phase_from_run
    _make_issue_ticket(ado_id=9116)
    from db import session_scope
    from models import Ticket
    with session_scope() as session:
        t = session.query(Ticket).filter(Ticket.ado_id == 9116).first()
        tid = t.id

    fake = _fake_ado_client()
    with patch("api.tickets._provider_for_ticket", return_value=None), \
         patch("api.tickets._ado_client_for_ticket", return_value=fake), \
         patch("config.config.STACKY_ISSUE_PHASE_COMMENTS_ENABLED", True):
        result = publish_issue_phase_from_run(
            ticket_id=tid,
            agent_type="technical",
            output="",
            project_name="Pacifico",
        )
    assert result is not None
    assert result["posted"] is False
    assert result["reason"] == "empty_output"
    fake.post_comment.assert_not_called()


def test_gitlab_provider_path(_app_ctx):
    """[C8] Rama GitLab: fake provider con `name` (string) → comment_exists con str(ado_id)."""
    from api.tickets import publish_issue_phase_from_run, _ISSUE_PHASE_MARKERS
    _make_issue_ticket(ado_id=9117)
    from db import session_scope
    from models import Ticket
    with session_scope() as session:
        t = session.query(Ticket).filter(Ticket.ado_id == 9117).first()
        tid = t.id

    fake_provider = _fake_provider(comment_exists_return=False)
    with patch("api.tickets._provider_for_ticket", return_value=fake_provider), \
         patch("config.config.STACKY_ISSUE_PHASE_COMMENTS_ENABLED", True):
        result = publish_issue_phase_from_run(
            ticket_id=tid,
            agent_type="technical",
            output="<h1>análisis técnico GitLab</h1>",
            project_name="Pacifico",
        )
    assert result is not None
    assert result["posted"] is True
    # Provider path: comment_exists llamado al menos una vez con str(ado_id) y marker
    # (se llama 2 veces: _marker_already_present + _post_phase_comment — por diseño)
    assert fake_provider.comment_exists.call_count >= 1
    first_call_args = fake_provider.comment_exists.call_args_list[0][0]
    assert first_call_args[0] == str(9117), f"Esperado str(9117), recibido {first_call_args[0]!r}"
    assert _ISSUE_PHASE_MARKERS["tecnico"] in first_call_args[1]
    # Provider path: post_comment(str(ado_id), marked_html) sin fmt
    fake_provider.post_comment.assert_called_once()
    post_args = fake_provider.post_comment.call_args[0]
    assert post_args[0] == str(9117)
    assert _ISSUE_PHASE_MARKERS["tecnico"] in post_args[1]


def test_never_raises_on_provider_error(_app_ctx):
    """Si _post_phase_comment lanza (error de DB/red inesperado), la función
    captura y devuelve posted=False con reason 'error:...', sin propagar.

    Nota: _post_phase_comment ya atrapa errores de post_comment internamente.
    Para testear el handler externo de publish_issue_phase_from_run, parcheamos
    _post_phase_comment directamente para que re-lance.
    """
    from api.tickets import publish_issue_phase_from_run
    _make_issue_ticket(ado_id=9118)
    from db import session_scope
    from models import Ticket
    with session_scope() as session:
        t = session.query(Ticket).filter(Ticket.ado_id == 9118).first()
        tid = t.id

    fake = _fake_ado_client(comment_exists_return=False)

    with patch("api.tickets._provider_for_ticket", return_value=None), \
         patch("api.tickets._ado_client_for_ticket", return_value=fake), \
         patch("api.tickets._post_phase_comment", side_effect=RuntimeError("DB timeout")), \
         patch("config.config.STACKY_ISSUE_PHASE_COMMENTS_ENABLED", True):
        # No debe lanzar
        result = publish_issue_phase_from_run(
            ticket_id=tid,
            agent_type="technical",
            output="<h1>algo</h1>",
            project_name="Pacifico",
        )
    assert result is not None
    assert result["posted"] is False
    assert "error" in result["reason"]


def test_raw_output_fallback_when_not_epic_shaped(_app_ctx):
    """[C9] Output sin estructura de épica → _extract_epic_html devuelve '' → se usa output crudo."""
    from api.tickets import publish_issue_phase_from_run, _ISSUE_PHASE_MARKERS
    _make_issue_ticket(ado_id=9119)
    from db import session_scope
    from models import Ticket
    with session_scope() as session:
        t = session.query(Ticket).filter(Ticket.ado_id == 9119).first()
        tid = t.id

    raw_output = "<p>análisis técnico sin estructura de épica</p>"
    fake = _fake_ado_client(comment_exists_return=False)
    with patch("api.tickets._provider_for_ticket", return_value=None), \
         patch("api.tickets._ado_client_for_ticket", return_value=fake), \
         patch("config.config.STACKY_ISSUE_PHASE_COMMENTS_ENABLED", True):
        result = publish_issue_phase_from_run(
            ticket_id=tid,
            agent_type="technical",
            output=raw_output,
            project_name="Pacifico",
        )
    assert result is not None
    assert result["posted"] is True
    # El comentario debe contener el output crudo (no vacío) y el marker
    posted_content = str(fake.post_comment.call_args)
    assert raw_output in posted_content or "análisis técnico" in posted_content
