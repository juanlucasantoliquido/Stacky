"""tests/test_plan94_variables_providers.py — Plan 94 F2.
Tests del sub-puerto CIVariablesProvider y adapters GitLab/ADO."""
import json
from pathlib import Path

import pytest
import unittest.mock as mock

import config
from services.ci_variables import VARIABLES_PORT_METHODS, get_variables_provider
from services.gitlab_variables import GitLabVariablesProvider
from services.ado_variables import AdoVariablesProvider
from services.ci_variables import VariablesUnavailableError
from services.tracker_provider import TrackerConfigError, TrackerApiError


@pytest.fixture
def mock_gitlab_client():
    """Mock del cliente GitLab (gitlab_client.py)."""
    with mock.patch("services.gitlab_variables.GitLabTrackerProvider") as mock_provider:
        mock_client = mock.MagicMock()
        mock_provider.return_value._client = mock_client
        mock_client._project_path.return_value = "mygroup/myproj"
        yield mock_client


@pytest.fixture
def mock_ado_client():
    """Mock del cliente ADO (ado_client.py)."""
    with mock.patch("services.ado_variables.AdoClient._request") as mock_request:
        yield mock_request


def test_f2_factory_by_tracker_type(monkeypatch):
    """Fábrica por tracker_type (patrón 93 F2 / espejo de get_ci_provider).

    Los imports de la fábrica son LAZY (C9) — from X import Y dentro de la
    función resuelve el atributo del módulo ORIGEN en el momento de la llamada,
    así que el patch va sobre services.gitlab_variables / services.ado_variables
    (no sobre services.ci_variables, que nunca tiene esos nombres como atributo
    propio). config también se patchea con monkeypatch.setattr sobre el objeto
    real (patrón test_plan71_ci_cache.py:88).
    """
    # GitLab: mock directo del provider en su módulo de origen
    # (name="..." es un kwarg reservado del constructor de Mock -- setea el repr,
    # NO el atributo .name -- por eso se asigna aparte).
    gitlab_stub = mock.MagicMock()
    gitlab_stub.name = "gitlab"
    with mock.patch("services.gitlab_variables.GitLabVariablesProvider", return_value=gitlab_stub):
        with mock.patch("services.project_context.resolve_project_context") as mock_ctx:
            mock_ctx.return_value.tracker_type = "gitlab"
            monkeypatch.setattr(config.config, "STACKY_GITLAB_ENABLED", True)
            provider = get_variables_provider("myproj")
            assert provider.name == "gitlab"

    # ADO: mock directo del provider en su módulo de origen
    ado_stub = mock.MagicMock()
    ado_stub.name = "azure_devops"
    with mock.patch("services.ado_variables.AdoVariablesProvider", return_value=ado_stub):
        with mock.patch("services.project_context.resolve_project_context") as mock_ctx:
            mock_ctx.return_value.tracker_type = "azure_devops"
            provider = get_variables_provider("myproj")
            assert provider.name == "azure_devops"

    # Tracker sin soporte ⇒ TrackerConfigError
    with mock.patch("services.project_context.resolve_project_context") as mock_ctx:
        mock_ctx.return_value.tracker_type = "jira"
        with pytest.raises(TrackerConfigError, match="no soporta variables CI"):
            get_variables_provider("myproj")


def test_f2_gitlab_list_never_returns_value(mock_gitlab_client):
    """GitLab list descarta value (write-only)."""
    # Fixture paginada (C2)
    mock_gitlab_client._request_paginated.return_value = [
        {"key": "DB_PASSWORD", "value": "S3cr3t!", "masked": True, "protected": False},
        {"key": "DEPLOY_PATH", "value": "/app", "masked": False, "protected": False},
        # §4 C5: secreta guardada con masked:false ⇒ is_secret False al refrescar
        {"key": "WEAK_SECRET", "value": "short", "masked": False, "protected": False},
    ]

    provider = GitLabVariablesProvider(project="myproj")
    result = provider.list_variables()

    assert len(result) == 3
    # Centinela §3.1: NUNCA aparece "value"
    assert all("value" not in item for item in result)
    assert "S3cr3t!" not in json.dumps(result)

    # is_secret correcto (masked or protected)
    assert result[0]["is_secret"] is True
    assert result[1]["is_secret"] is False
    # C5: masked=false + protected=false ⇒ is_secret False
    assert result[2]["is_secret"] is False


def test_f2_gitlab_set_post_then_put(mock_gitlab_client):
    """C3: POST si no existe (404), PUT si existe (200)."""
    provider = GitLabVariablesProvider(project="myproj")

    # Caso 1: no existe (404) ⇒ POST
    mock_gitlab_client._request.side_effect = [
        TrackerApiError(404, "Not found", kind="not_found"),
        ({"key": "NEW_VAR"}, 201),
    ]
    result = provider.set_variable("NEW_VAR", "val", False)
    assert mock_gitlab_client._request.call_count == 2
    # Primer call: GET para detectar existencia
    assert mock_gitlab_client._request.call_args_list[0][0][0] == "GET"
    # Segundo call: POST para crear
    assert mock_gitlab_client._request.call_args_list[1][0][0] == "POST"
    assert result["key"] == "NEW_VAR"

    # Caso 2: existe (200) ⇒ PUT
    mock_gitlab_client._request.reset_mock()
    mock_gitlab_client._request.side_effect = [
        ({"key": "EXISTING"}, 200),
        ({"key": "EXISTING"}, 200),
    ]
    result = provider.set_variable("EXISTING", "val2", False)
    assert mock_gitlab_client._request.call_count == 2
    assert mock_gitlab_client._request.call_args_list[1][0][0] == "PUT"


def test_f2_gitlab_masked_rejected_fallback(mock_gitlab_client):
    """C8: reintento con masked=false si status 400.

    C3: set_variable SIEMPRE hace primero el GET de existencia (aquí: existe,
    200 ⇒ verbo PUT), así que la secuencia real es GET + PUT(masked:true, 400)
    + PUT(masked:false, 200) = 3 llamadas.
    """
    provider = GitLabVariablesProvider(project="myproj")

    mock_gitlab_client._request.side_effect = [
        ({"key": "WEAK"}, 200),  # GET existencia (C3) ⇒ existe ⇒ PUT
        TrackerApiError(400, "Masked not allowed", kind="masked_rejected"),  # PUT masked:true
        ({"key": "WEAK"}, 200),  # retry PUT masked:false
    ]

    result = provider.set_variable("WEAK", "short", True)
    assert mock_gitlab_client._request.call_count == 3
    # Ambos intentos de mutación llevan raw:true (A3); el GET de existencia no lleva json=
    first_call_body = mock_gitlab_client._request.call_args_list[1][1]["json"]
    assert first_call_body["raw"] is True
    second_call_body = mock_gitlab_client._request.call_args_list[2][1]["json"]
    assert second_call_body["raw"] is True
    # El retorno tiene masked:false
    assert result["masked"] is False


def test_f2_gitlab_secret_sends_raw_true(mock_gitlab_client):
    """A3: secret=True envía raw=True (evita expansión de $)."""
    provider = GitLabVariablesProvider(project="myproj")
    mock_gitlab_client._request.return_value = ({"key": "PASS"}, 200)

    # Secret=True ⇒ raw en el body
    provider.set_variable("PASS", "pa$$word", True)
    call_body = mock_gitlab_client._request.call_args[1]["json"]
    assert call_body.get("raw") is True

    # Secret=False ⇒ sin raw
    mock_gitlab_client._request.reset_mock()
    provider.set_variable("PATH", "/usr/bin", False)
    call_body = mock_gitlab_client._request.call_args[1]["json"]
    assert "raw" not in call_body


def test_f2_gitlab_delete_404_false(mock_gitlab_client):
    """DELETE retorna False si 404."""
    provider = GitLabVariablesProvider(project="myproj")
    mock_gitlab_client._request.side_effect = TrackerApiError(404, "Not found", kind="not_found")
    assert provider.delete_variable("MISSING") is False


def test_f2_ado_no_definition_raises_unavailable():
    """ADO sin definition ⇒ VariablesUnavailableError."""
    # Mock find_yaml_definition ⇒ None
    with mock.patch("services.ado_variables.find_yaml_definition", return_value=None):
        with pytest.raises(VariablesUnavailableError, match="plan 95"):
            get_variables_provider("myproj")


def test_f2_ado_list_maps_is_secret():
    """ADO list mapea isSecret correctamente."""
    with mock.patch("services.ado_variables.find_yaml_definition", return_value={"id": 123}):
        mock_client = mock.MagicMock()
        mock_client.return_value = (
            {
                "id": 123,
                "variables": {
                    "DB_PASSWORD": {"isSecret": True, "value": None},  # secreto
                    "DEPLOY_PATH": {"isSecret": False, "value": "/app"},
                },
            },
            200,
        )

        with mock.patch("services.ado_variables.AdoClient._request", return_value=mock_client.return_value):
            provider = AdoVariablesProvider(project="myproj")
            result = provider.list_variables()

            assert len(result) == 2
            assert result[0]["is_secret"] is True
            assert result[0]["key"] == "DB_PASSWORD"
            assert result[1]["is_secret"] is False
            assert result[1]["key"] == "DEPLOY_PATH"


def test_f2_ado_set_merges_full_definition():
    """C4: PUT lleva el documento completo con revision."""
    with mock.patch("services.ado_variables.find_yaml_definition", return_value={"id": 123, "revision": 5}):
        # GET devuelve definition con revision
        get_response = {
            "id": 123,
            "revision": 5,
            "variables": {"OLD_VAR": {"isSecret": False, "value": "/old"}},
        }

        with mock.patch(
            "services.ado_variables.AdoClient._request",
            side_effect=[(get_response, 200), ({"key": "NEW_VAR"}, 200)],
        ) as mock_request:
            provider = AdoVariablesProvider(project="myproj")
            provider.set_variable("NEW_VAR", "newval", False)

            # Verificar que el PUT tiene el documento completo
            assert mock_request.call_count == 2
            put_body = mock_request.call_args_list[1][1]["json"]
            assert put_body["revision"] == 5  # C4: revision intacto
            assert "OLD_VAR" in put_body["variables"]  # anti-lost-update
            assert "NEW_VAR" in put_body["variables"]


def test_f2_ado_set_preserves_secret_sibling():
    """C12: NO borra secretos hermanos (value:null se conserva)."""
    with mock.patch("services.ado_variables.find_yaml_definition", return_value={"id": 123, "revision": 5}):
        # GET trae variable hermana secreta
        get_response = {
            "id": 123,
            "revision": 5,
            "variables": {
                "OTRA_SECRETA": {"value": None, "isSecret": True},  # C12
                "NEW_VAR": {"value": None, "isSecret": False},
            },
        }

        with mock.patch(
            "services.ado_variables.AdoClient._request",
            side_effect=[(get_response, 200), ({"key": "NEW_VAR"}, 200)],
        ) as mock_request:
            provider = AdoVariablesProvider(project="myproj")
            provider.set_variable("NEW_VAR", "v", False)

            put_body = mock_request.call_args_list[1][1]["json"]
            # C12: OTRA_SECRETA viaja byte-idéntica
            assert put_body["variables"]["OTRA_SECRETA"]["value"] is None
            assert put_body["variables"]["OTRA_SECRETA"]["isSecret"] is True


def test_f2_ado_delete_absent_false():
    """DELETE retorna False si la key no existe."""
    with mock.patch("services.ado_variables.find_yaml_definition", return_value={"id": 123}):
        mock_client = mock.MagicMock()
        get_response = {
            "id": 123,
            "variables": {"EXISTING": {"isSecret": False, "value": "/old"}},
        }
        mock_client.side_effect = [(get_response, 200)]

        with mock.patch("services.ado_variables.AdoClient._request", side_effect=mock_client.side_effect):
            provider = AdoVariablesProvider(project="myproj")
            assert provider.delete_variable("MISSING") is False


def test_f2_port_structural_conformance():
    """Patrón test_plan73_repo_writer.py:34-44."""
    assert hasattr(GitLabVariablesProvider, "list_variables")
    assert hasattr(GitLabVariablesProvider, "set_variable")
    assert hasattr(GitLabVariablesProvider, "delete_variable")
    assert hasattr(AdoVariablesProvider, "list_variables")
    assert hasattr(AdoVariablesProvider, "set_variable")
    assert hasattr(AdoVariablesProvider, "delete_variable")
    assert VARIABLES_PORT_METHODS == ("list_variables", "set_variable", "delete_variable")


def test_f2_no_value_in_exceptions():
    """Centinela §3.1: excepciones NO contienen el value."""
    # GitLab
    with mock.patch("services.gitlab_variables.GitLabTrackerProvider") as mock_provider:
        mock_client = mock.MagicMock()
        mock_provider.return_value._client = mock_client
        mock_client._project_path.return_value = "p"
        mock_client._request.side_effect = RuntimeError("boom S3cr3t!XYZ")

        provider = GitLabVariablesProvider(project="p")
        with pytest.raises(TrackerApiError) as exc_info:
            provider.set_variable("K", "S3cr3t!XYZ", True)
        # El mensaje NO contiene el secreto (sanitizado)
        assert "S3cr3t!XYZ" not in str(exc_info.value)
        assert "Error interno" in str(exc_info.value)  # mensaje genérico

    # ADO
    with mock.patch("services.ado_variables.AdoClient._request") as mock_request:
        mock_request.side_effect = RuntimeError("boom S3cr3t!XYZ")
        with mock.patch("services.ado_variables.find_yaml_definition", return_value={"id": 1}):
            provider = AdoVariablesProvider(project="p")
            with pytest.raises(TrackerApiError) as exc_info:
                provider.set_variable("K", "S3cr3t!XYZ", True)
            assert "S3cr3t!XYZ" not in str(exc_info.value)
            assert "Error interno" in str(exc_info.value)
