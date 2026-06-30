"""
tests/test_gitlab_client.py -- Tests del cliente HTTP GitLab (Plan 65 F2).

Todos los tests mockean requests — sin red.
"""
import pytest
from unittest.mock import MagicMock, patch

from services.tracker_provider import TrackerConfigError, TrackerApiError


class _FakeHeaders:
    """Headers proxy que soporta .get() y es iterable."""
    def __init__(self, d: dict):
        self._d = d

    def get(self, k, d=None):
        return self._d.get(k, d)

    def __iter__(self):
        return iter(self._d)

    def items(self):
        return self._d.items()


def _make_resp(status_code=200, json_body=None, headers=None, text=""):
    """Crea un MagicMock que emula requests.Response con headers correctos."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = (200 <= status_code < 300)
    resp.headers = _FakeHeaders(headers or {})
    resp.content = b'{"ok":true}' if json_body is not None else b""
    resp.text = text

    _jb = json_body

    def _json():
        if _jb is not None:
            return _jb
        raise ValueError("no JSON body")

    resp.json = _json
    return resp


def test_headers_use_private_token(monkeypatch):
    """_headers() devuelve PRIVATE-TOKEN con el token cargado."""
    monkeypatch.setenv("GITLAB_TOKEN", "glpat-abc123")
    monkeypatch.setenv("GITLAB_URL", "https://gitlab.example.com")
    from importlib import reload
    import services.gitlab_client as mod
    reload(mod)
    client = mod.GitLabClient(base_url="https://gitlab.example.com", project="123")
    h = client._headers()
    assert h["PRIVATE-TOKEN"] == "glpat-abc123"
    assert h["Accept"] == "application/json"


def test_project_path_urlencodes_slash_path(monkeypatch):
    """Paths con '/' se URL-encodean; IDs numéricos se dejan intactos."""
    monkeypatch.setenv("GITLAB_TOKEN", "tok")
    monkeypatch.setenv("GITLAB_URL", "https://gl.example.com")
    from importlib import reload
    import services.gitlab_client as mod
    reload(mod)

    c1 = mod.GitLabClient(base_url="https://gl.example.com", project="grp/sub/proj")
    assert c1._project_path() == "grp%2Fsub%2Fproj"

    c2 = mod.GitLabClient(base_url="https://gl.example.com", project="123")
    assert c2._project_path() == "123"


def test_pagination_follows_x_next_page(monkeypatch):
    """_request_paginated concatena 3 páginas siguiendo X-Next-Page."""
    monkeypatch.setenv("GITLAB_TOKEN", "tok")
    monkeypatch.setenv("GITLAB_URL", "https://gl.example.com")
    from importlib import reload
    import services.gitlab_client as mod
    reload(mod)
    client = mod.GitLabClient(base_url="https://gl.example.com", project="123")

    pages = [
        ([{"id": 1}], {"X-Next-Page": "2", "Content-Type": "application/json"}),
        ([{"id": 2}], {"X-Next-Page": "3", "Content-Type": "application/json"}),
        ([{"id": 3}], {"X-Next-Page": "", "Content-Type": "application/json"}),
    ]
    call_count = [0]

    def fake_request(method, url, **kwargs):
        idx = call_count[0]
        call_count[0] += 1
        body, hdrs = pages[idx]
        return _make_resp(200, json_body=body, headers=hdrs)

    with patch("requests.request", side_effect=fake_request):
        results = client._request_paginated("/issues")

    assert len(results) == 3
    assert results[0]["id"] == 1
    assert results[2]["id"] == 3


def test_retry_honors_retry_after_on_429(monkeypatch):
    """Un 429 con Retry-After:0 se reintenta y el 200 siguiente pasa."""
    monkeypatch.setenv("GITLAB_TOKEN", "tok")
    monkeypatch.setenv("GITLAB_URL", "https://gl.example.com")
    from importlib import reload
    import services.gitlab_client as mod
    reload(mod)
    client = mod.GitLabClient(base_url="https://gl.example.com", project="123")

    call_count = [0]

    def fake_request(method, url, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return _make_resp(
                429,
                json_body={"message": "rate limited"},
                headers={"Retry-After": "0", "Content-Type": "application/json"},
                text="rate limited",
            )
        return _make_resp(200, json_body={"id": 42}, headers={"Content-Type": "application/json"})

    with patch("requests.request", side_effect=fake_request), \
         patch("time.sleep"):
        body, _ = client._request("GET", "/projects/123")

    assert body == {"id": 42}
    assert call_count[0] == 2


def test_error_mapping_taxonomy(monkeypatch):
    """401→auth, 404→not_found, 429→rate_limited, 503→server."""
    monkeypatch.setenv("GITLAB_TOKEN", "tok")
    monkeypatch.setenv("GITLAB_URL", "https://gl.example.com")
    from importlib import reload
    import services.gitlab_client as mod
    reload(mod)
    client = mod.GitLabClient(base_url="https://gl.example.com", project="123")

    cases = [
        (401, "auth"),
        (404, "not_found"),
        (429, "rate_limited"),
        (503, "server"),
    ]

    for status_code, expected_kind in cases:
        sc = status_code  # capturar en closure

        def fake_request(method, url, _sc=sc, **kwargs):
            return _make_resp(
                _sc,
                json_body={"message": f"error {_sc}"},
                text=f"error {_sc}",
            )

        with patch("requests.request", side_effect=fake_request), \
             patch("time.sleep"):
            with pytest.raises(TrackerApiError) as exc_info:
                client._request("GET", "/test")
        assert exc_info.value.status == status_code, f"status mismatch for {status_code}"
        assert exc_info.value.kind == expected_kind, f"kind mismatch for {status_code}"


def test_missing_token_raises_config_error(monkeypatch):
    """Sin GITLAB_TOKEN y sin archivo auth → TrackerConfigError."""
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    monkeypatch.setenv("GITLAB_URL", "https://gl.example.com")
    from importlib import reload
    import services.gitlab_client as mod
    reload(mod)
    with pytest.raises(TrackerConfigError):
        mod.GitLabClient(base_url="https://gl.example.com", project="123")
