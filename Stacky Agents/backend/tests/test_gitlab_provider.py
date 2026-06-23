"""
tests/test_gitlab_provider.py -- Tests del adapter GitLabTrackerProvider (Plan 65 F3..F9).

Todos los tests mockean GitLabClient — sin red.
"""
import pytest
from unittest.mock import MagicMock, patch, call

from services.tracker_provider import TrackerItem, TrackerQuery


def _make_provider(project="123", group="", epics_native=False):
    """Crea GitLabTrackerProvider con GitLabClient completamente mockeado."""
    from services.gitlab_provider import GitLabTrackerProvider
    with patch("services.gitlab_provider.GitLabClient") as mock_cls, \
         patch("services.gitlab_provider.config") as mock_cfg:
        mock_cfg.GITLAB_URL = "https://gl.example.com"
        mock_cfg.GITLAB_PROJECT = project
        mock_cfg.STACKY_GITLAB_GROUP = group
        mock_cfg.STACKY_GITLAB_EPICS_NATIVE = epics_native
        mock_client = MagicMock()
        mock_client._base_url = "https://gl.example.com"
        mock_client._project_path.return_value = project
        mock_client._token = "tok"
        mock_cls.return_value = mock_client
        provider = GitLabTrackerProvider(project=project)
    return provider, mock_client


# ── F3: Consulta ──────────────────────────────────────────────────────────────

def test_fetch_open_items_translates_query():
    """fetch_open_items transforma TrackerQuery a params de GitLab."""
    provider, mock_client = _make_provider()
    mock_client._request_paginated.return_value = [
        {"id": 1, "iid": 1, "title": "Tarea", "state": "opened",
         "description": "<p>d</p>", "labels": ["type::task"],
         "assignees": [], "web_url": "http://gl/1", "updated_at": "2026-01-01"}
    ]

    q = TrackerQuery(state="open", labels=("type::task",), assignee="juanluca")
    results = provider.fetch_open_items(q)

    call_args = mock_client._request_paginated.call_args
    params = call_args.kwargs.get("params") or (call_args.args[1] if len(call_args.args) > 1 else {})
    assert params.get("state") == "opened"
    assert "juanluca" in params.get("assignee_username", "")
    assert len(results) == 1
    assert results[0]["title"] == "Tarea"


def test_create_item_sets_type_label():
    """create_item agrega un label type::<item_type> al issue de GitLab."""
    provider, mock_client = _make_provider()
    created = {
        "id": 10, "iid": 10, "title": "Mi épica", "state": "opened",
        "description": "<p>d</p>", "labels": ["type::epic"],
        "assignees": [], "web_url": "http://gl/10", "updated_at": "2026-01-01",
    }
    mock_client._request.return_value = (created, {})

    item = TrackerItem(item_type="epic", title="Mi épica", description_html="<p>d</p>")
    result = provider.create_item(item)

    call_args = mock_client._request.call_args
    json_body = call_args.kwargs.get("json_body") or {}
    labels_sent = json_body.get("labels", "")
    assert "type::epic" in labels_sent
    assert result["title"] == "Mi épica"


def test_create_item_with_parent_calls_link():
    """create_item con parent_id llama a _link_parent."""
    provider, mock_client = _make_provider()
    created = {
        "id": 11, "iid": 11, "title": "Child", "state": "opened",
        "description": "", "labels": [], "assignees": [],
        "web_url": "http://gl/11", "updated_at": "2026-01-01",
    }
    mock_client._request.return_value = (created, {})
    mock_client._request_paginated.return_value = []  # para el link

    item = TrackerItem(
        item_type="task", title="Child", description_html="<p>c</p>", parent_id="5"
    )

    # Mockear _link_parent directamente
    with patch.object(provider, "_link_parent") as mock_link:
        provider.create_item(item)

    mock_link.assert_called_once_with("11", "5")


def test_update_item_state_maps_logical_to_label_and_close():
    """update_item_state 'accepted' cierra el issue y agrega el label."""
    provider, mock_client = _make_provider()
    # GET para obtener labels actuales
    current = {"labels": ["other_label"], "description": "desc"}
    updated = {
        "id": 1, "iid": 1, "title": "T", "state": "closed",
        "description": "desc", "labels": ["other_label", "stacky::accepted"],
        "assignees": [], "web_url": "http://gl/1", "updated_at": "2026-06-01",
    }
    mock_client._request.side_effect = [
        (current, {}),  # GET actual labels
        (updated, {}),  # PUT update
    ]

    result = provider.update_item_state("1", "accepted")

    # El segundo call debe incluir state_event=close
    put_call = mock_client._request.call_args_list[1]
    json_body = put_call.kwargs.get("json_body") or {}
    assert json_body.get("state_event") == "close"
    assert "stacky::accepted" in json_body.get("labels", "")


def test_normalize_issue_shape():
    """_normalize_issue devuelve el shape canónico."""
    provider, _ = _make_provider()
    raw = {
        "id": 42,
        "iid": 3,
        "title": "Bug X",
        "description": "<p>bug</p>",
        "state": "opened",
        "labels": ["bug", "type::bug"],
        "assignees": [{"username": "dev1"}],
        "web_url": "http://gl/42",
        "updated_at": "2026-06-20T00:00:00",
        "epic": {"iid": 5},
    }
    result = provider._normalize_issue(raw)
    assert result["id"] == "42"
    assert result["iid"] == "3"
    assert result["state"] == "opened"
    assert result["assignees"] == ["dev1"]
    assert result["parent"] == "5"


def test_get_authenticated_user_shape():
    """get_authenticated_user devuelve shape canónico."""
    provider, mock_client = _make_provider()
    mock_client._request.return_value = (
        {"id": 7, "username": "juanluca", "name": "Juan Luca", "email": "j@example.com"},
        {},
    )
    result = provider.get_authenticated_user()
    assert result["username"] == "juanluca"
    assert result["id"] == "7"


# ── F4: Comentarios ───────────────────────────────────────────────────────────

def test_comment_exists_finds_marker():
    """comment_exists devuelve True cuando el marker está en una nota."""
    provider, mock_client = _make_provider()
    mock_client._request_paginated.return_value = [
        {"id": 1, "body": "contenido ::marker_abc:: fin", "system": False},
    ]
    assert provider.comment_exists("10", "::marker_abc::") is True


def test_comment_exists_false_when_absent():
    """comment_exists devuelve False cuando no encuentra el marker."""
    provider, mock_client = _make_provider()
    mock_client._request_paginated.return_value = [
        {"id": 1, "body": "otro contenido", "system": False},
    ]
    assert provider.comment_exists("10", "::marker_xyz::") is False


def test_fetch_comments_excludes_system_notes():
    """fetch_comments excluye notas con system=True."""
    provider, mock_client = _make_provider()
    mock_client._request_paginated.return_value = [
        {"id": 1, "body": "nota normal", "system": False},
        {"id": 2, "body": "moved issue", "system": True},
    ]
    results = provider.fetch_comments("5")
    assert len(results) == 1
    assert results[0]["id"] == 1


def test_post_comment_preserves_marker_substring():
    """post_comment pasa el body sin modificar el marker."""
    provider, mock_client = _make_provider()
    marker_body = "<p>Nota con ::stacky-marker:: único</p>"
    mock_client._request.return_value = ({"id": 99, "body": marker_body}, {})

    result = provider.post_comment("7", marker_body)

    call_args = mock_client._request.call_args
    json_body = call_args.kwargs.get("json_body") or {}
    assert "::stacky-marker::" in json_body.get("body", "")
    assert result.get("id") == 99


# ── F5: Attachments ───────────────────────────────────────────────────────────

def test_upload_returns_markdown_and_url(tmp_path):
    """upload_attachment retorna markdown y url."""
    provider, mock_client = _make_provider()
    test_file = tmp_path / "test.txt"
    test_file.write_text("contenido")
    mock_client._request.return_value = (
        {"alt": "test.txt", "url": "/uploads/abc/test.txt", "markdown": "![test.txt](/uploads/abc/test.txt)"},
        {},
    )
    result = provider.upload_attachment(str(test_file), "test.txt")
    assert "markdown" in result or "url" in result


def test_link_attachment_appends_to_description():
    """link_attachment agrega el markdown del attachment a la descripción."""
    provider, mock_client = _make_provider()
    mock_client._request.side_effect = [
        ({"description": "desc inicial", "id": 1, "iid": 1, "title": "T",
          "state": "opened", "labels": [], "assignees": [], "web_url": "", "updated_at": ""}, {}),
        ({"description": "desc inicial\n\n![f.txt](/uploads/abc/f.txt)", "id": 1, "iid": 1,
          "title": "T", "state": "opened", "labels": [], "assignees": [], "web_url": "", "updated_at": ""}, {}),
    ]
    result = provider.link_attachment("1", {"markdown": "![f.txt](/uploads/abc/f.txt)"})
    put_call = mock_client._request.call_args_list[1]
    json_body = put_call.kwargs.get("json_body") or {}
    assert "![f.txt]" in json_body.get("description", "")


def test_fetch_attachments_parses_upload_links():
    """fetch_attachments extrae links de upload de la descripción."""
    provider, mock_client = _make_provider()
    desc = "Texto\n\n![archivo.pdf](/uploads/abc123/archivo.pdf)\n![img.png](/uploads/xyz/img.png)"
    mock_client._request.return_value = (
        {"description": desc, "id": 1, "iid": 1, "title": "T",
         "state": "opened", "labels": [], "assignees": [], "web_url": "", "updated_at": ""},
        {},
    )
    results = provider.fetch_attachments("1")
    assert len(results) == 2
    assert any("archivo.pdf" in r["name"] for r in results)


# ── F6: Assignees ─────────────────────────────────────────────────────────────

def test_resolve_assignee_id_by_username():
    """_resolve_assignee_id resuelve username a ID."""
    provider, mock_client = _make_provider()
    mock_client._request.return_value = ([{"id": 42, "username": "dev1"}], {})
    result = provider._resolve_assignee_id("dev1")
    assert result == 42


def test_update_assignee_sets_assignee_ids():
    """update_item_assignee envía assignee_ids con el ID resuelto."""
    provider, mock_client = _make_provider()
    mock_client._request.side_effect = [
        ([{"id": 55, "username": "dev2"}], {}),   # /users?username=dev2
        ({"id": 1, "iid": 1, "title": "T", "state": "opened",
          "description": "", "labels": [], "assignees": [{"username": "dev2"}],
          "web_url": "", "updated_at": ""}, {}),  # PUT update
    ]
    result = provider.update_item_assignee("1", "dev2")
    put_call = mock_client._request.call_args_list[1]
    json_body = put_call.kwargs.get("json_body") or {}
    assert json_body.get("assignee_ids") == [55]


def test_unknown_username_clears_assignee():
    """Si username no resuelve a ID, se limpia la asignación."""
    provider, mock_client = _make_provider()
    mock_client._request.side_effect = [
        ([], {}),  # /users?username=desconocido → lista vacía
        ({"id": 1, "iid": 1, "title": "T", "state": "opened",
          "description": "", "labels": [], "assignees": [],
          "web_url": "", "updated_at": ""}, {}),
    ]
    provider.update_item_assignee("1", "desconocido")
    put_call = mock_client._request.call_args_list[1]
    json_body = put_call.kwargs.get("json_body") or {}
    assert json_body.get("assignee_ids") == []


# ── F7: Jerarquía ─────────────────────────────────────────────────────────────

def test_link_parent_uses_issue_links_in_fallback():
    """_link_parent en modo fallback (no native epics) usa /issues/{id}/links."""
    provider, mock_client = _make_provider(epics_native=False)
    mock_client._request.return_value = ({}, {})
    provider._link_parent("10", "5")
    call_args = mock_client._request.call_args
    path = call_args.args[1] if call_args.args else ""
    assert "/links" in path


def test_link_parent_uses_group_epic_when_native_and_group_set():
    """_link_parent con native epics + group usa /groups/{g}/epics/{id}/issues."""
    provider, mock_client = _make_provider(group="mygroup", epics_native=True)
    mock_client._request.return_value = ({}, {})
    provider._link_parent("10", "5")
    call_args = mock_client._request.call_args
    path = call_args.args[1] if call_args.args else ""
    assert "/groups/mygroup/epics" in path or "epics" in path


def test_native_epics_403_degrades_to_fallback():
    """Si el endpoint de epic nativo devuelve 403, degrada a issue-links."""
    provider, mock_client = _make_provider(group="mygroup", epics_native=True)
    from services.tracker_provider import TrackerApiError

    call_count = [0]

    def side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise TrackerApiError(403, "Forbidden", kind="auth")
        return ({}, {})

    mock_client._request.side_effect = side_effect
    provider._link_parent("10", "5")
    # Debe haber habido 2 llamadas: una al epic endpoint (403) y una al fallback
    assert call_count[0] == 2


def test_find_child_by_marker_matches_description_or_comment():
    """find_child_by_marker retorna el issue cuando el marker está en un link."""
    provider, mock_client = _make_provider()
    linked_issue = {
        "id": 99, "iid": 99, "title": "Child",
        "description": "Texto con ::mi-marker:: aquí",
        "state": "opened", "labels": [], "assignees": [],
        "web_url": "http://gl/99", "updated_at": "2026-01-01",
    }
    mock_client._request.return_value = ([linked_issue], {})
    mock_client._request_paginated.return_value = []

    result = provider.find_child_by_marker("5", "::mi-marker::")
    assert result is not None
    assert result["iid"] == "99"


# ── F8: Updates ───────────────────────────────────────────────────────────────

def test_fetch_item_updates_merges_and_sorts():
    """fetch_item_updates combina label+state events y los ordena por created_at."""
    provider, mock_client = _make_provider()

    def _paginated_side(path, **kwargs):
        if "resource_label_events" in path:
            return [{"created_at": "2026-06-15T10:00:00", "action": "add",
                     "label": {"name": "bug"}, "user": {"username": "dev"}}]
        if "resource_state_events" in path:
            return [{"created_at": "2026-06-14T09:00:00", "state": "closed",
                     "user": {"username": "dev"}}]
        if "/notes" in path:
            return []
        return []

    mock_client._request_paginated.side_effect = _paginated_side

    results = provider.fetch_item_updates("10")
    # Ordenados por created_at: state (09:00) primero, label (10:00) después
    assert len(results) >= 2
    assert results[0]["kind"] == "state_event"
    assert results[1]["kind"] == "label_event"


def test_fetch_item_updates_filters_by_since():
    """fetch_item_updates filtra por since cuando se provee."""
    provider, mock_client = _make_provider()

    def _paginated_side(path, **kwargs):
        if "resource_label_events" in path:
            return [
                {"created_at": "2026-06-01T00:00:00", "action": "add",
                 "label": {"name": "old"}, "user": {"username": "u"}},
                {"created_at": "2026-06-20T00:00:00", "action": "add",
                 "label": {"name": "new"}, "user": {"username": "u"}},
            ]
        if "resource_state_events" in path:
            return []
        return []

    mock_client._request_paginated.side_effect = _paginated_side

    results = provider.fetch_item_updates("10", since="2026-06-10T00:00:00")
    assert len(results) == 1
    assert results[0]["label"]["name"] == "new"


def test_label_event_normalized_shape():
    """Los label events tienen kind, created_at, label, action, user."""
    provider, mock_client = _make_provider()

    def _paginated_side(path, **kwargs):
        if "resource_label_events" in path:
            return [{"created_at": "2026-06-20T00:00:00", "action": "add",
                     "label": {"name": "bug"}, "user": {"username": "dev"}}]
        return []

    mock_client._request_paginated.side_effect = _paginated_side

    results = provider.fetch_item_updates("5")
    label_evs = [r for r in results if r["kind"] == "label_event"]
    assert label_evs
    ev = label_evs[0]
    assert "kind" in ev
    assert "created_at" in ev
    assert "label" in ev
    assert "action" in ev
    assert "user" in ev


# ── F9: Pipelines ─────────────────────────────────────────────────────────────

def test_fetch_pipelines_normalizes():
    """fetch_pipelines devuelve shape canónico."""
    provider, mock_client = _make_provider()
    mock_client._request_paginated.return_value = [
        {"id": 1, "status": "success", "ref": "main", "sha": "abc",
         "web_url": "http://gl/pipelines/1", "created_at": "2026-06-01",
         "updated_at": "2026-06-01"},
    ]
    results = provider.fetch_pipelines()
    assert len(results) == 1
    assert results[0]["status"] == "success"
    assert results[0]["id"] == "1"


def test_infer_pipeline_uses_ci_when_gitlab():
    """fetch_pipelines acepta ref para filtrar por rama."""
    provider, mock_client = _make_provider()
    mock_client._request_paginated.return_value = []
    result = provider.fetch_pipelines(ref="develop")
    # Verifica que se pasó ref como parámetro
    call_args = mock_client._request_paginated.call_args
    params = call_args.kwargs.get("params") or {}
    assert params.get("ref") == "develop"
    assert result == []


def test_infer_pipeline_falls_back_to_llm_when_no_ci():
    """Cuando GitLab CI no tiene pipelines (lista vacía), infer_pipeline
    cae al fallback LLM en lugar de devolver lista vacía."""
    provider, mock_client = _make_provider()
    mock_client._request_paginated.return_value = []  # CI sin pipelines

    result = provider.infer_pipeline()

    # El fallback debe devolver al menos un ítem con "source" == "llm"
    # (la implementación usa un pipeline genérico cuando CI está vacío)
    assert isinstance(result, list)
    assert len(result) > 0
    sources = [p.get("source") for p in result]
    assert "llm" in sources
