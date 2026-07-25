"""Transporte HTTP falso, guiado por fixtures grabados. Plan 218 F3.

NO mockea providers ni el módulo `config` (P4): dobla el TRANSPORTE, que es lo único
que el contrato tiene derecho a falsear. Los adaptadores corren de verdad.
"""
from __future__ import annotations

import json
import urllib.error
from http.client import HTTPMessage
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

_FIXTURES_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "provider_contract"


class _Expectation:
    __slots__ = ("method", "url_substring", "status", "body", "headers", "consumed")

    def __init__(self, method, url_substring, status, body, headers):
        self.method = method.upper()
        self.url_substring = url_substring
        self.status = status
        self.body = body
        self.headers = headers or {}
        self.consumed = False


class FakeHttp:
    """Router determinista (método, substring de URL) -> (status, body, headers).

    Las expectativas se consumen EN ORDEN: registrar dos veces la misma ruta permite
    modelar paginación o un 429 seguido de un 200. La última expectativa que matchea
    queda reutilizable (así una ruta estable no necesita registrarse N veces).
    """

    def __init__(self, fixtures_dir: str | Path | None = None, provider: str = ""):
        self.provider = provider
        self._fixtures_dir = Path(fixtures_dir) if fixtures_dir else (_FIXTURES_ROOT / provider)
        self._expectations: list[_Expectation] = []
        self._calls: list[dict] = []

    # ── API pública ───────────────────────────────────────────────────────────

    def expect(
        self,
        method: str,
        url_substring: str,
        *,
        status: int,
        body: Any,
        headers: Optional[dict] = None,
    ) -> "FakeHttp":
        self._expectations.append(_Expectation(method, url_substring, status, body, headers))
        return self

    def calls(self) -> list[dict]:
        """[{'method','url','headers','body'}] — permite asertar la forma real del request."""
        return list(self._calls)

    def fixture(self, name: str) -> Any:
        path = self._fixtures_dir / f"{name}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def reset(self) -> "FakeHttp":
        self._expectations.clear()
        self._calls.clear()
        return self

    # ── Ruteo ─────────────────────────────────────────────────────────────────

    def _resolve(self, method: str, url: str) -> _Expectation:
        candidatas = [
            e for e in self._expectations
            if e.method == method.upper() and e.url_substring in url
        ]
        if not candidatas:
            return _Expectation(
                method, url, 404,
                {"message": f"FakeHttp: ruta no registrada {method} {url}"}, None,
            )
        pendientes = [e for e in candidatas if not e.consumed]
        elegida = pendientes[0] if pendientes else candidatas[-1]
        elegida.consumed = True
        return elegida

    def _record(self, method: str, url: str, headers: dict, body: Any) -> None:
        self._calls.append({"method": method.upper(), "url": url, "headers": headers, "body": body})


# ── ADO: urllib ───────────────────────────────────────────────────────────────

class _FakeUrlopenResponse:
    def __init__(self, status: int, raw: str, url: str, content_type: str):
        self.status = status
        self._raw = raw.encode("utf-8")
        self._url = url
        self.headers = HTTPMessage()
        self.headers["Content-Type"] = content_type

    def read(self) -> bytes:
        return self._raw

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def install_for_ado(monkeypatch, fake: FakeHttp) -> None:
    """Parchea el ATRIBUTO urllib.request.urlopen (no un call-site).

    C13: el v1 enumeraba 'ado_client.py:271,537'; los sitios reales son 4 y enumerarlos
    es frágil. Parchear el atributo del módulo cubre todos y sobrevive a cualquier
    renumeración.
    """
    import urllib.request

    def _fake_urlopen(req, timeout=None):  # noqa: ARG001
        url = req.full_url
        method = req.get_method()
        body = None
        if req.data:
            try:
                body = json.loads(req.data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                body = req.data
        fake._record(method, url, dict(req.headers), body)

        exp = fake._resolve(method, url)
        content_type = exp.headers.get("Content-Type", "application/json")
        raw = exp.body if isinstance(exp.body, str) else json.dumps(exp.body)

        if 200 <= exp.status < 300:
            final_url = exp.headers.get("X-Final-Url", url)
            return _FakeUrlopenResponse(exp.status, raw, final_url, content_type)

        hdrs = HTTPMessage()
        for k, v in exp.headers.items():
            if k not in ("X-Final-Url",):
                hdrs[k] = str(v)
        raise urllib.error.HTTPError(url, exp.status, "fake", hdrs, BytesIO(raw.encode("utf-8")))

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)


# ── GitLab: requests ──────────────────────────────────────────────────────────

class _FakeRequestsResponse:
    def __init__(self, status: int, body: Any, headers: dict):
        self.status_code = status
        self._body = body
        self.headers = dict(headers)
        self.headers.setdefault("Content-Type", "application/json")

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 400

    @property
    def text(self) -> str:
        return self._body if isinstance(self._body, str) else json.dumps(self._body)

    @property
    def content(self) -> bytes:
        return self.text.encode("utf-8")

    def json(self) -> Any:
        if isinstance(self._body, str):
            return json.loads(self._body)
        return self._body


def install_for_gitlab(monkeypatch, fake: FakeHttp) -> None:
    """Parchea el ATRIBUTO requests.request (usado en gitlab_client.py:135)."""
    import requests

    def _fake_request(method, url, **kwargs):
        fake._record(method, url, kwargs.get("headers") or {}, kwargs.get("json"))
        exp = fake._resolve(method, url)
        return _FakeRequestsResponse(exp.status, exp.body, exp.headers)

    monkeypatch.setattr(requests, "request", _fake_request)
