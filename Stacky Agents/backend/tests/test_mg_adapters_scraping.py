"""tests/test_mg_adapters_scraping.py — Plan 217 F2b (PRIMERO, C6).

Valida `tools/migrar_mantis_gitlab/adapters/scraping_adapter.py`:
login Mantis en 2 pasos (usuario -> contraseña), fallo de login,
parsing de listado (`view_all_bug_page.php`) y detalle (`view.php`)
usando los fixtures HTML anonimizados de `fixtures/mg/`, y re-login
automático ante sesión expirada a mitad de una corrida (C7).

Mockea `requests.Session` inyectada por constructor (no hay red real).
"""
from __future__ import annotations

import pathlib
from unittest.mock import MagicMock

import pytest

from tools.migrar_mantis_gitlab.adapters.scraping_adapter import (
    MantisScrapingAuthError,
    MantisWebScrapingReadAdapter,
)

_FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "mg"
_BASE_URL = "https://mantis.ejemplo.local/mantis"

# HTML sintético mínimo de las páginas de login (2 pasos) — sin datos reales.
_LOGIN_PAGE_HTML = (
    '<html><body><form action="login.php" method="post">'
    '<input type="hidden" name="csrf_token" value="tok-paso1"/>'
    '<input type="text" name="username"/>'
    '<button>Login</button></form></body></html>'
)
_LOGIN_PASSWORD_PAGE_HTML = (
    '<html><body><form action="login_password_page.php" method="post">'
    '<input type="hidden" name="csrf_token" value="tok-paso2"/>'
    '<input type="hidden" name="username" value="testuser"/>'
    '<input type="password" name="password"/></form></body></html>'
)
_LOGGED_IN_HOME_HTML = "<html><body><h1>Bienvenido, testuser</h1></body></html>"


class _FakeResponse:
    def __init__(self, text: str, *, headers: dict | None = None, content: bytes | None = None) -> None:
        self.text = text
        # Por defecto se comporta como una respuesta HTML (mismo criterio
        # que los tests preexistentes, que solo miran `.text`); los tests
        # de `download_attachment_binary` (Batch 4) pasan `headers`/
        # `content` explícitos para simular una respuesta binaria real.
        self.headers = headers if headers is not None else {"Content-Type": "text/html"}
        self.content = content if content is not None else text.encode("utf-8")


def _load_fixture(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def _make_session(get_map: dict[str, str], post_map: dict[str, str]) -> MagicMock:
    """Sesión mockeada: `get_map`/`post_map` mapean URL exacta -> HTML de
    respuesta. Lanza AssertionError ante una URL no contemplada (evita
    falsos verdes por mocks demasiado permisivos)."""
    session = MagicMock()

    def fake_get(url, timeout=None):
        if url not in get_map:
            raise AssertionError(f"GET inesperado en el mock: {url}")
        return _FakeResponse(get_map[url])

    def fake_post(url, data=None, timeout=None):
        if url not in post_map:
            raise AssertionError(f"POST inesperado en el mock: {url}")
        return _FakeResponse(post_map[url])

    session.get.side_effect = fake_get
    session.post.side_effect = fake_post
    return session


def _happy_path_login_maps() -> tuple[dict[str, str], dict[str, str]]:
    get_map = {f"{_BASE_URL}/login_page.php": _LOGIN_PAGE_HTML}
    post_map = {
        f"{_BASE_URL}/login.php": _LOGIN_PASSWORD_PAGE_HTML,
        f"{_BASE_URL}/login_password_page.php": _LOGGED_IN_HOME_HTML,
    }
    return get_map, post_map


# ── Login exitoso ───────────────────────────────────────────────────────


def test_login_exitoso_autentica_y_expone_sesion():
    get_map, post_map = _happy_path_login_maps()
    session = _make_session(get_map, post_map)

    adapter = MantisWebScrapingReadAdapter(
        _BASE_URL, [310], "testuser", "correcthorsebattery", session=session
    )
    returned_session = adapter.get_session()

    assert returned_session is session
    assert session.get.call_count == 1
    assert session.post.call_count == 2


# ── Login fallido (credenciales malas) ───────────────────────────────────


def test_login_fallido_credenciales_malas_lanza_auth_error():
    get_map = {f"{_BASE_URL}/login_page.php": _LOGIN_PAGE_HTML}
    post_map = {
        f"{_BASE_URL}/login.php": _LOGIN_PASSWORD_PAGE_HTML,
        # Contraseña incorrecta: Mantis vuelve a servir la página de login.
        f"{_BASE_URL}/login_password_page.php": _LOGIN_PAGE_HTML,
    }
    session = _make_session(get_map, post_map)

    adapter = MantisWebScrapingReadAdapter(
        _BASE_URL, [310], "testuser", "contraseña-incorrecta", session=session
    )
    with pytest.raises(MantisScrapingAuthError, match="contraseña"):
        adapter.get_session()


def test_login_fallido_usuario_invalido_lanza_auth_error_en_paso1():
    get_map = {f"{_BASE_URL}/login_page.php": _LOGIN_PAGE_HTML}
    post_map = {
        # Usuario inexistente: Mantis vuelve a servir la página de login ya
        # en el paso 1 (nunca llega a pedir contraseña).
        f"{_BASE_URL}/login.php": _LOGIN_PAGE_HTML,
    }
    session = _make_session(get_map, post_map)

    adapter = MantisWebScrapingReadAdapter(
        _BASE_URL, [310], "usuario-inexistente", "cualquiera", session=session
    )
    with pytest.raises(MantisScrapingAuthError, match="usuario"):
        adapter.get_session()


# ── Listado parseado correctamente ───────────────────────────────────────


def test_fetch_all_issues_parsea_listado_con_conteo_e_ids():
    list_html = _load_fixture("mantis_view_all_bug_page_sample.html")
    get_map, post_map = _happy_path_login_maps()
    get_map[f"{_BASE_URL}/view_all_bug_page.php?project_id=310"] = list_html
    session = _make_session(get_map, post_map)

    adapter = MantisWebScrapingReadAdapter(
        _BASE_URL, [310], "testuser", "correcthorsebattery", session=session
    )
    issues = adapter.fetch_all_issues()

    assert len(issues) == 3
    assert [i["id"] for i in issues] == [1001, 1002, 1003]
    assert issues[0]["summary"] == "Fallo al generar reporte mensual de ejemplo"
    assert issues[0]["status"] == "new"
    assert issues[0]["priority"] == "high"
    assert issues[1]["status"] == "resolved"
    assert all(i["project_id"] == 310 for i in issues)


# ── Detalle parseado correctamente ───────────────────────────────────────


def test_fetch_issue_detail_y_metodos_del_contrato_parsean_detalle():
    detail_html = _load_fixture("mantis_view_page_sample.html")
    get_map, post_map = _happy_path_login_maps()
    get_map[f"{_BASE_URL}/view.php?id=1001"] = detail_html
    session = _make_session(get_map, post_map)

    adapter = MantisWebScrapingReadAdapter(
        _BASE_URL, [310], "testuser", "correcthorsebattery", session=session
    )

    detail = adapter.fetch_issue_detail(1001)
    assert detail["reporter"] == "reportero.demo"
    assert detail["handler"] == "responsable.demo"
    assert detail["status"] == "new"
    assert detail["description"] == "Descripcion de ejemplo del ticket de prueba numero uno."
    assert len(detail["notes"]) == 2
    assert detail["notes"][0]["reporter"] == "Usuario Ejemplo"
    assert detail["attachments"][0]["name"] == "captura_pantalla_demo.png"
    assert detail["attachments"][0]["id"] == "501"
    assert detail["relationships"][0]["type"] == "related to"
    assert detail["relationships"][0]["target_issue_id"] == 1002

    # Los 3 métodos del contrato MantisReadAdapter reusan el mismo parsing.
    assert adapter.fetch_comments(1001)[1]["text"] == (
        "Segunda nota de ejemplo confirmando el problema."
    )
    assert adapter.fetch_attachments(1001)[0]["size"] == 120480
    assert adapter.fetch_relationships(1001)[0]["target_issue_id"] == 1002


# ── Re-login automático ante sesión expirada (C7) ────────────────────────


def test_relogin_automatico_ante_sesion_expirada_a_mitad_de_corrida():
    detail_html = _load_fixture("mantis_view_page_sample.html")
    view_url = f"{_BASE_URL}/view.php?id=1001"
    login_page_calls = {"n": 0}
    view_calls = {"n": 0}

    def fake_get(url, timeout=None):
        if url == f"{_BASE_URL}/login_page.php":
            login_page_calls["n"] += 1
            return _FakeResponse(_LOGIN_PAGE_HTML)
        if url == view_url:
            view_calls["n"] += 1
            if view_calls["n"] == 1:
                # Sesión "expirada": el 1er intento devuelve la página de login.
                return _FakeResponse(_LOGIN_PAGE_HTML)
            return _FakeResponse(detail_html)
        raise AssertionError(f"GET inesperado en el mock: {url}")

    def fake_post(url, data=None, timeout=None):
        if url == f"{_BASE_URL}/login.php":
            return _FakeResponse(_LOGIN_PASSWORD_PAGE_HTML)
        if url == f"{_BASE_URL}/login_password_page.php":
            return _FakeResponse(_LOGGED_IN_HOME_HTML)
        raise AssertionError(f"POST inesperado en el mock: {url}")

    session = MagicMock()
    session.get.side_effect = fake_get
    session.post.side_effect = fake_post

    adapter = MantisWebScrapingReadAdapter(
        _BASE_URL, [310], "testuser", "correcthorsebattery", session=session
    )
    # Simula que ya se autenticó antes, en una corrida larga.
    adapter.get_session()
    assert login_page_calls["n"] == 1

    # El caller NUNCA ve el fallo: recibe el detalle correcto igual.
    detail = adapter.fetch_issue_detail(1001)

    assert detail["reporter"] == "reportero.demo"
    assert login_page_calls["n"] == 2, "Debió re-loguear automáticamente una vez más"
    assert view_calls["n"] == 2, "Debió reintentar la request original tras el re-login"


# ── download_attachment_binary (Batch 4, F6a) ────────────────────────────

_PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-binary-content"


def test_download_attachment_binary_descarga_bytes_crudos():
    get_map, post_map = _happy_path_login_maps()
    download_url = f"{_BASE_URL}/file_download.php?file_id=501"
    session = _make_session(get_map, post_map)

    def fake_get(url, timeout=None):
        if url == download_url:
            return _FakeResponse("", headers={"Content-Type": "image/png"}, content=_PNG_BYTES)
        if url not in get_map:
            raise AssertionError(f"GET inesperado en el mock: {url}")
        return _FakeResponse(get_map[url])

    session.get.side_effect = fake_get

    adapter = MantisWebScrapingReadAdapter(
        _BASE_URL, [310], "testuser", "correcthorsebattery", session=session
    )
    result = adapter.download_attachment_binary("501")

    assert result == _PNG_BYTES


def test_download_attachment_binary_relogin_automatico_ante_sesion_expirada():
    download_url = f"{_BASE_URL}/file_download.php?file_id=501"
    login_page_calls = {"n": 0}
    download_calls = {"n": 0}

    def fake_get(url, timeout=None):
        if url == f"{_BASE_URL}/login_page.php":
            login_page_calls["n"] += 1
            return _FakeResponse(_LOGIN_PAGE_HTML)
        if url == download_url:
            download_calls["n"] += 1
            if download_calls["n"] == 1:
                # Sesión "expirada": el 1er intento devuelve la página de login.
                return _FakeResponse(_LOGIN_PAGE_HTML)
            return _FakeResponse("", headers={"Content-Type": "image/png"}, content=_PNG_BYTES)
        raise AssertionError(f"GET inesperado en el mock: {url}")

    def fake_post(url, data=None, timeout=None):
        if url == f"{_BASE_URL}/login.php":
            return _FakeResponse(_LOGIN_PASSWORD_PAGE_HTML)
        if url == f"{_BASE_URL}/login_password_page.php":
            return _FakeResponse(_LOGGED_IN_HOME_HTML)
        raise AssertionError(f"POST inesperado en el mock: {url}")

    session = MagicMock()
    session.get.side_effect = fake_get
    session.post.side_effect = fake_post

    adapter = MantisWebScrapingReadAdapter(
        _BASE_URL, [310], "testuser", "correcthorsebattery", session=session
    )
    adapter.get_session()
    assert login_page_calls["n"] == 1

    result = adapter.download_attachment_binary("501")

    assert result == _PNG_BYTES
    assert login_page_calls["n"] == 2, "Debió re-loguear automáticamente una vez más"
    assert download_calls["n"] == 2, "Debió reintentar la descarga tras el re-login"


def test_download_attachment_binary_lanza_si_relogin_tambien_falla():
    download_url = f"{_BASE_URL}/file_download.php?file_id=501"
    get_map, post_map = _happy_path_login_maps()
    # Cualquier intento de descarga sigue devolviendo la página de login,
    # incluso después del re-login.
    get_map[download_url] = _LOGIN_PAGE_HTML
    session = _make_session(get_map, post_map)

    adapter = MantisWebScrapingReadAdapter(
        _BASE_URL, [310], "testuser", "correcthorsebattery", session=session
    )
    with pytest.raises(MantisScrapingAuthError, match="adjunto"):
        adapter.download_attachment_binary("501")
