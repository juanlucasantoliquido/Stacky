"""Tests Q1.2 — Few-shot de outputs aprobados en runtimes CLI.

TDD para `_inject_cli_fewshot` y `_cli_fewshot_enabled` en
`services/context_enrichment.py`.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def _fake_example(exec_id=1):
    from services.few_shot import FewShotExample
    return FewShotExample(
        execution_id=exec_id,
        agent_type="developer",
        title_hint="Task anterior",
        output="Output de ejemplo " * 10,
    )


# ---------------------------------------------------------------------------
# _cli_fewshot_enabled
# ---------------------------------------------------------------------------

def test_fewshot_enabled_returns_true():
    import services.context_enrichment as ce
    mock_config = MagicMock()
    mock_config.STACKY_CLI_FEWSHOT_ENABLED = True
    mock_config.STACKY_CLI_FEWSHOT_PROJECTS = ""
    with patch("config.config", mock_config):
        assert ce._cli_fewshot_enabled("any") is True


def test_fewshot_disabled_returns_false():
    import services.context_enrichment as ce
    mock_config = MagicMock()
    mock_config.STACKY_CLI_FEWSHOT_ENABLED = False
    mock_config.STACKY_CLI_FEWSHOT_PROJECTS = ""
    with patch("config.config", mock_config):
        assert ce._cli_fewshot_enabled("any") is False


def test_fewshot_project_allowlist_filters():
    import services.context_enrichment as ce
    mock_config = MagicMock()
    mock_config.STACKY_CLI_FEWSHOT_ENABLED = True
    mock_config.STACKY_CLI_FEWSHOT_PROJECTS = "proj_a,proj_b"
    with patch("config.config", mock_config):
        assert ce._cli_fewshot_enabled("proj_a") is True
        assert ce._cli_fewshot_enabled("proj_c") is False


# ---------------------------------------------------------------------------
# _inject_cli_fewshot
# ---------------------------------------------------------------------------

def test_injects_block_when_examples_exist():
    """≥1 aprobada → bloque 'few-shot-approved' presente."""
    examples = [_fake_example(1), _fake_example(2)]

    with (
        patch("services.context_enrichment._cli_fewshot_enabled", return_value=True),
        patch("services.few_shot.pick_examples", return_value=examples),
        patch("services.few_shot.build_prefix", return_value="## Ejemplos..."),
    ):
        from services.context_enrichment import _inject_cli_fewshot
        blocks = _inject_cli_fewshot(
            ticket_id=1,
            agent_type="developer",
            project_name="PROJ",
            blocks=[],
            log=lambda *a, **kw: None,
        )

    ids = [b.get("id") for b in blocks]
    assert "few-shot-approved" in ids


def test_noop_when_no_examples():
    """Sin aprobadas → no-op."""
    with (
        patch("services.context_enrichment._cli_fewshot_enabled", return_value=True),
        patch("services.few_shot.pick_examples", return_value=[]),
    ):
        from services.context_enrichment import _inject_cli_fewshot
        blocks = _inject_cli_fewshot(
            ticket_id=1,
            agent_type="developer",
            project_name="PROJ",
            blocks=[],
            log=lambda *a, **kw: None,
        )
    assert not any(b.get("id") == "few-shot-approved" for b in blocks)


def test_flag_off_byte_identical():
    """Flag OFF → byte-idéntico."""
    with patch("services.context_enrichment._cli_fewshot_enabled", return_value=False):
        from services.context_enrichment import _inject_cli_fewshot
        blocks_in = [{"id": "existing", "content": "x"}]
        blocks_out = _inject_cli_fewshot(
            ticket_id=1,
            agent_type="developer",
            project_name="PROJ",
            blocks=blocks_in,
            log=lambda *a, **kw: None,
        )
    assert blocks_out is blocks_in


def test_exclude_ticket_id_passed():
    """El ticket_id del run se pasa a pick_examples para excluirlo."""
    with (
        patch("services.context_enrichment._cli_fewshot_enabled", return_value=True),
        patch("services.few_shot.pick_examples") as mock_pick,
        patch("services.few_shot.build_prefix", return_value=""),
    ):
        mock_pick.return_value = []
        from services.context_enrichment import _inject_cli_fewshot
        _inject_cli_fewshot(
            ticket_id=42,
            agent_type="developer",
            project_name="PROJ",
            blocks=[],
            log=lambda *a, **kw: None,
        )
    call_kwargs = mock_pick.call_args[1]
    assert call_kwargs.get("exclude_ticket_id") == 42


def test_idempotent():
    """Bloque ya presente → no duplicar."""
    with patch("services.context_enrichment._cli_fewshot_enabled", return_value=True):
        from services.context_enrichment import _inject_cli_fewshot
        existing = [{"id": "few-shot-approved", "content": "ya existe"}]
        blocks_out = _inject_cli_fewshot(
            ticket_id=1,
            agent_type="developer",
            project_name="PROJ",
            blocks=existing,
            log=lambda *a, **kw: None,
        )
    count = sum(1 for b in blocks_out if b.get("id") == "few-shot-approved")
    assert count == 1


def test_copilot_path_not_duplicated():
    """El bloque few-shot-approved viene de enrich_blocks; copilot usa agents/base.py.
    Verificamos que el inyector de contexto no duplica si ya viene del copilot path."""
    with patch("services.context_enrichment._cli_fewshot_enabled", return_value=True):
        from services.context_enrichment import _inject_cli_fewshot
        already_from_copilot = [{"id": "few-shot-approved", "content": "copilot prefix"}]
        out = _inject_cli_fewshot(
            ticket_id=1,
            agent_type="developer",
            project_name="PROJ",
            blocks=already_from_copilot,
            log=lambda *a, **kw: None,
        )
    assert sum(1 for b in out if b.get("id") == "few-shot-approved") == 1
