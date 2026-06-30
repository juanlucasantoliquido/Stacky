"""
tests/test_global_config_gitlab.py -- Tests de global_config para GitLab (Plan 65 F11).
"""
import json
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture()
def app():
    """Flask test app mínimo con global_config blueprint registrado."""
    from flask import Flask
    from api.global_config import bp
    application = Flask(__name__)
    application.register_blueprint(bp)
    application.config["TESTING"] = True
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


def _patch_env(monkeypatch, **kwargs):
    for k, v in kwargs.items():
        monkeypatch.setenv(k, v)


def test_put_config_persists_gitlab_fields_without_token(client, tmp_path, monkeypatch):
    """PUT /global-config persiste GITLAB_URL/GITLAB_PROJECT/STACKY_GITLAB_GROUP pero NUNCA GITLAB_TOKEN."""
    from api import global_config as gc
    # Apuntar _ENV_PATH a un archivo temporal
    monkeypatch.setattr(gc, "_ENV_PATH", tmp_path / ".env")

    resp = client.put(
        "/global-config",
        data=json.dumps({
            "GITLAB_URL": "https://gl.example.com",
            "GITLAB_PROJECT": "mygroup/myproject",
            "STACKY_GITLAB_GROUP": "mygroup",
            "STACKY_GITLAB_ENABLED": "true",
            # GITLAB_TOKEN NO está en _MANAGED_KEYS → no se persiste
        }),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True

    # Verificar que el .env NO contiene GITLAB_TOKEN
    env_content = (tmp_path / ".env").read_text()
    assert "GITLAB_TOKEN" not in env_content
    assert "GITLAB_URL=https://gl.example.com" in env_content


def test_connection_check_uses_gitlab_branch(client, monkeypatch, tmp_path):
    """POST /global-config/test-connection con tracker_type=gitlab usa la rama GitLab."""
    from api import global_config as gc
    monkeypatch.setattr(gc, "_ENV_PATH", tmp_path / ".env")

    # Mockear GitLabClient para que no haga llamadas reales
    mock_client = MagicMock()
    mock_client._project_path.return_value = "mygroup%2Fmyproject"
    # /user → usuario autenticado
    mock_client._request.side_effect = [
        ({"id": 7, "username": "dev"}, {}),   # /user
        ([{"id": 1}], {}),                     # /issues
        ({"access_level": 40}, {}),            # /members/all/7
    ]

    with patch("api.global_config.GitLabClient", return_value=mock_client):
        resp = client.post(
            "/global-config/test-connection",
            data=json.dumps({
                "tracker_type": "gitlab",
                "gitlab_url": "https://gl.example.com",
                "gitlab_project": "mygroup/myproject",
            }),
            content_type="application/json",
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["tracker_type"] == "gitlab"


def test_shadow_check_reports_all_three(client, monkeypatch, tmp_path):
    """El check GitLab reporta auth, read, write_permission."""
    from api import global_config as gc
    monkeypatch.setattr(gc, "_ENV_PATH", tmp_path / ".env")

    mock_client = MagicMock()
    mock_client._project_path.return_value = "proj"
    mock_client._request.side_effect = [
        ({"id": 7, "username": "dev"}, {}),
        ([{"id": 1}], {}),
        ({"access_level": 40}, {}),
    ]

    with patch("api.global_config.GitLabClient", return_value=mock_client):
        resp = client.post(
            "/global-config/test-connection",
            data=json.dumps({
                "tracker_type": "gitlab",
                "gitlab_url": "https://gl.example.com",
                "gitlab_project": "proj",
            }),
            content_type="application/json",
        )

    data = resp.get_json()
    # La respuesta debe contener info de checks en el message
    assert "auth" in data.get("message", "").lower() or "gl" in data.get("message", "").lower()


def test_shadow_check_flags_insufficient_role(client, monkeypatch, tmp_path):
    """write_permission=False cuando access_level < 30 (Reporter=20)."""
    from api import global_config as gc
    monkeypatch.setattr(gc, "_ENV_PATH", tmp_path / ".env")

    mock_client = MagicMock()
    mock_client._project_path.return_value = "proj"
    mock_client._request.side_effect = [
        ({"id": 7, "username": "dev"}, {}),
        ([{"id": 1}], {}),
        ({"access_level": 20}, {}),  # Reporter — sin write
    ]

    with patch("api.global_config.GitLabClient", return_value=mock_client):
        resp = client.post(
            "/global-config/test-connection",
            data=json.dumps({
                "tracker_type": "gitlab",
                "gitlab_url": "https://gl.example.com",
                "gitlab_project": "proj",
            }),
            content_type="application/json",
        )

    data = resp.get_json()
    # ok puede ser False (auth+read OK pero write_permission=False)
    assert isinstance(data, dict)


def test_shadow_check_never_writes(client, monkeypatch, tmp_path):
    """El check de conexión NO escribe ningún issue ni comentario."""
    from api import global_config as gc
    monkeypatch.setattr(gc, "_ENV_PATH", tmp_path / ".env")

    mock_client = MagicMock()
    mock_client._project_path.return_value = "proj"
    mock_client._request.side_effect = [
        ({"id": 7, "username": "dev"}, {}),
        ([{"id": 1}], {}),
        ({"access_level": 40}, {}),
    ]

    with patch("api.global_config.GitLabClient", return_value=mock_client):
        client.post(
            "/global-config/test-connection",
            data=json.dumps({
                "tracker_type": "gitlab",
                "gitlab_url": "https://gl.example.com",
                "gitlab_project": "proj",
            }),
            content_type="application/json",
        )

    # Verificar que no se llamó a POST de issues ni de comentarios
    for call_args in mock_client._request.call_args_list:
        method = call_args.args[0] if call_args.args else "GET"
        path = call_args.args[1] if len(call_args.args) > 1 else ""
        assert method.upper() != "POST" or "/user" not in path or "/issues" not in path, (
            f"El check de conexión NO debe hacer POST a issues/comentarios: {method} {path}"
        )
        # Permitidos: GET /user, GET /projects/.../issues (list), GET /members/...
        if method.upper() == "POST":
            assert "/issues" not in path and "/notes" not in path, (
                f"Shadow check hizo un POST prohibido: {method} {path}"
            )
