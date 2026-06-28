"""Plan 70 F8 -- Grupo creacion: provider branches para create_item.

Sites migrados:
  - _publish_epic_to_ado: provider.create_item(TrackerItem(item_type="Epic"))
  - _publish_issue_to_ado: provider.create_item(TrackerItem(item_type="Issue"))
  - _ensure_task_creation_parent: provider.create_item para intermedios
  - publish_epic_children: provider.create_item para Feature/Task hijos

Patron aplicado (GAP-E):
    _provider = _provider_for_ticket(...)
    if _provider is not None:
        wi = _provider.create_item(_tracker_item_from_kwargs(...))
    else:
        wi = <ado/client>.create_work_item(...)

Fallback ADO: Flag OFF o provider no disponible -> comportamiento identico al pre-plan.
"""
from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

TICKETS = pathlib.Path(__file__).resolve().parents[1] / "api" / "tickets.py"


def test_tickets_module_imports_cleanly():
    import api.tickets  # noqa: F401


def test_epic_create_has_provider_branch():
    """Branch provider.create_item para Epic presente en tickets.py."""
    text = TICKETS.read_text(encoding="utf-8")
    assert "_provider.create_item(" in text or "provider.create_item(" in text, (
        "F8: branch provider para create_item no encontrado en tickets.py"
    )


def test_issue_create_has_provider_branch():
    """_publish_issue_to_ado tiene branch provider."""
    text = TICKETS.read_text(encoding="utf-8")
    # Ambas funciones (epic + issue) usan _provider.create_item
    count = text.count("_provider.create_item(")
    assert count >= 2, (
        f"F8: se esperaban >=2 branches provider (create_item) para epic+issue, "
        f"encontrados {count}"
    )


def test_publish_epic_children_has_provider_branch():
    """publish_epic_children tiene branch provider para Feature/Task."""
    text = TICKETS.read_text(encoding="utf-8")
    assert "_provider.find_child_by_marker(" in text, (
        "F8: publish_epic_children debe usar _provider.find_child_by_marker"
    )


def test_ensure_task_creation_parent_has_provider_branch():
    """_ensure_task_creation_parent tiene branch provider para intermedios."""
    text = TICKETS.read_text(encoding="utf-8")
    assert "if provider is not None:" in text, (
        "F8: _ensure_task_creation_parent debe tener branch 'if provider is not None:'"
    )


def test_create_item_uses_tracker_item_from_kwargs():
    """Los branches provider usan _tracker_item_from_kwargs para adaptar la firma."""
    text = TICKETS.read_text(encoding="utf-8")
    assert "_tracker_item_from_kwargs(" in text


def test_publish_epic_provider_mock():
    """Flag ON: _publish_epic_to_ado llama provider.create_item con TrackerItem Epic."""
    import api.tickets as tickets

    mock_provider = MagicMock(name="gitlab")
    mock_provider.create_item.return_value = {
        "id": 42,
        "fields": {"System.Title": "Mi Epic"},
        "_links": {"html": {"href": "https://gitlab.com/issues/42"}},
    }
    mock_provider.item_url.return_value = "https://gitlab.com/issues/42"

    with patch("api.tickets._provider_for_ticket", return_value=mock_provider), \
         patch("api.tickets._persist_epic_ticket"), \
         patch("api.tickets._epic_brief_save"):
        result = tickets._publish_epic_to_ado(
            description_html="<h1>Titulo</h1>",
            brief="Brief",
            project_name="test-project",
            title="Mi Epic",
        )

    mock_provider.create_item.assert_called_once()
    call_args = mock_provider.create_item.call_args[0][0]
    assert call_args.item_type == "Epic"
    assert result.ado_id == 42


def test_publish_epic_flag_off_uses_ado():
    """Flag OFF: _publish_epic_to_ado usa _ado_client_for_ticket (byte-identico)."""
    import api.tickets as tickets

    mock_client = MagicMock()
    mock_client.create_work_item.return_value = {
        "id": 99,
        "fields": {"System.Title": "Epic ADO"},
        "_links": {"html": {"href": "https://ado.com/99"}},
    }

    with patch("api.tickets._provider_for_ticket", return_value=None), \
         patch("api.tickets._ado_client_for_ticket", return_value=mock_client), \
         patch("api.tickets._persist_epic_ticket"), \
         patch("api.tickets._epic_brief_save"):
        result = tickets._publish_epic_to_ado(
            description_html="<h1>X</h1>",
            brief="B",
            project_name="p",
        )

    mock_client.create_work_item.assert_called_once()
    assert result.ado_id == 99


def test_publish_issue_provider_mock():
    """Flag ON: _publish_issue_to_ado llama provider.create_item con TrackerItem Issue."""
    import api.tickets as tickets

    mock_provider = MagicMock(name="gitlab")
    mock_provider.create_item.return_value = {
        "id": 77,
        "fields": {"System.Title": "Mi Issue"},
        "_links": {},
    }
    mock_provider.item_url.return_value = "https://gitlab.com/issues/77"

    with patch("api.tickets._provider_for_ticket", return_value=mock_provider), \
         patch("api.tickets._persist_issue_ticket"), \
         patch("api.tickets._epic_brief_save"):
        result = tickets._publish_issue_to_ado(
            description_html="<h1>Issue</h1>",
            brief="Brief",
            project_name="p",
        )

    call_args = mock_provider.create_item.call_args[0][0]
    assert call_args.item_type == "Issue"
    assert result.ado_id == 77


def test_publish_epic_children_provider_mock():
    """Flag ON: publish_epic_children usa _provider.create_item para Feature/Task."""
    import api.tickets as tickets

    mock_provider = MagicMock(name="gitlab")
    mock_provider.find_child_by_marker.return_value = None  # no hay existente
    mock_provider.create_item.return_value = {"id": 10}

    # ChildNodePreview(work_item_type, title, html, children)
    feature_node = tickets.ChildNodePreview(
        work_item_type="Feature",
        title="F1",
        html="<p>f</p>",
        children=[
            tickets.ChildNodePreview(work_item_type="Task", title="T1", html="<p>t</p>")
        ],
    )
    children_plan = tickets.EpicChildrenPlan(
        ok=True,
        features=[feature_node],
        total_children=2,
    )

    with patch("api.tickets._provider_for_ticket", return_value=mock_provider), \
         patch("api.tickets._epic_decomposition_enabled", return_value=True):
        result = tickets.publish_epic_children(
            epic_ado_id=5,
            children_plan=children_plan,
            project_name="p",
        )

    # El provider fue llamado con create_item al menos para la Feature
    assert mock_provider.create_item.called
    assert result.error is None


def test_publish_epic_children_flag_off_uses_ado():
    """Flag OFF: publish_epic_children usa ado.create_work_item (byte-identico)."""
    import api.tickets as tickets

    mock_ado = MagicMock()
    mock_ado.find_child_by_marker.return_value = None
    mock_ado.create_work_item.return_value = {"id": 20}

    feature_node = tickets.ChildNodePreview(
        work_item_type="Feature",
        title="F2",
        html="<p>f</p>",
    )
    children_plan = tickets.EpicChildrenPlan(
        ok=True,
        features=[feature_node],
        total_children=1,
    )

    with patch("api.tickets._provider_for_ticket", return_value=None), \
         patch("api.tickets._epic_decomposition_enabled", return_value=True):
        result = tickets.publish_epic_children(
            epic_ado_id=5,
            children_plan=children_plan,
            project_name="p",
            ado=mock_ado,
        )

    mock_ado.create_work_item.assert_called()
    assert result.error is None
