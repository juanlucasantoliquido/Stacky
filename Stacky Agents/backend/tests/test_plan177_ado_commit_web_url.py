"""Plan 177 F1 — regresión del bug `_base_project_url` en `ado_provider.commit_file`.

El AdoClient REAL define SOLO `_base_proj` (no `_base_project_url`). `commit_file`
armaba el `web_url` de retorno con `client._base_project_url` → `AttributeError`
DESPUÉS de que el push ya aterminó, disfrazado de `TrackerApiError(ado_push_failed)`.
El fake de abajo NO define `_base_project_url` a propósito (no es un MagicMock, que
autocrearía cualquier atributo): si el código volviera a usar el atributo inexistente,
estos tests rompen con AttributeError. Espeja el arnés de `test_plan95_ado_parity.py`
pero SIN el monkeypatch de `_base_project_url` (esa era justamente la trampa).
"""
import base64

from unittest.mock import patch


class _FakeAdoClient:
    """Fake mínimo del AdoClient real: define `_base_proj`, NO `_base_project_url`."""

    def __init__(self, side_effect):
        self._base_proj = "https://dev.azure.com/test-org/test-project"
        self._side_effect = side_effect
        self.calls = []

    def _request(self, method, url, body=None):
        self.calls.append((method, url, body))
        result = self._side_effect(method, url, body)
        if isinstance(result, Exception):
            raise result
        return result


def _make_provider(side_effect):
    from services.ado_provider import AdoTrackerProvider

    fake = _FakeAdoClient(side_effect)
    with patch("services.ado_provider.build_ado_client", return_value=fake):
        provider = AdoTrackerProvider(project="test-project")
    return provider, fake


def test_commit_file_add_returns_web_url_without_attribute_error():
    """Branch nuevo + item 404 (add) + push OK ⇒ status 'create' y web_url con /_git/
    construido desde `_base_proj` — SIN AttributeError ni ado_push_failed."""

    def side_effect(method, url, body=None):
        if "refs" in url and "filter=heads/feature" in url:
            return {"value": []}  # branch no existe
        if "refs" in url and "filter=heads/main" in url:
            return {"value": [{"objectId": "base-sha"}]}
        if method == "POST" and "refs" in url:
            return {}  # crea la rama
        if "items" in url:
            return Exception("404")  # no existe ⇒ add
        if "pushes" in url:
            return {"commits": [{"commitId": "new-sha"}]}
        return Exception(f"unexpected {method} {url}")

    with patch("services.ado_pipeline_definitions._resolve_repo_id", return_value="repo-1"), \
         patch("services.ado_pipeline_definitions._default_branch", return_value="main"):
        provider, _fake = _make_provider(side_effect)
        result = provider.commit_file("src/fix.py", "print('x')", "feature/inc-1", "fix")

    assert result["status"] == "create"
    assert result["sha"] == "new-sha"
    assert "/_git/" in result["web_url"]
    assert "version=GBfeature/inc-1" in result["web_url"]
    assert result["web_url"].startswith("https://dev.azure.com/test-org/test-project")


def test_commit_file_unchanged_uses_base_proj():
    """Item con contenido idéntico ⇒ status 'unchanged' y web_url desde `_base_proj`
    (sin crash y sin push)."""
    identical = "print('x')"

    def side_effect(method, url, body=None):
        if "refs" in url:
            return {"value": [{"objectId": "base-sha"}]}
        if "items" in url:
            return {"content": base64.b64encode(identical.encode()).decode()}
        return Exception("no push expected")

    with patch("services.ado_pipeline_definitions._resolve_repo_id", return_value="repo-1"):
        provider, fake = _make_provider(side_effect)
        result = provider.commit_file("src/fix.py", identical, "main", "same")

    assert result["status"] == "unchanged"
    assert "/_git/" in result["web_url"]
    assert not any("pushes" in c[1] for c in fake.calls)
