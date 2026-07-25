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
# La ESTRUCTURA replica la verificada en vivo contra una instancia Mantis real
# (no una inventada): `login_page.php` postea el usuario a
# `login_password_page.php`, y ESA página postea la contraseña a `login.php`.
# Antes estaba invertido, y por eso los tests pasaban contra un flujo que
# jamás habría autenticado contra un Mantis de verdad.
_LOGIN_PAGE_HTML = (
    '<html><body><form id="login-form" method="post" action="login_password_page.php">'
    '<input type="hidden" name="return" value="index.php"/>'
    '<input type="hidden" name="csrf_token" value="tok-paso1"/>'
    '<input id="username" name="username" type="text"/>'
    '<input type="submit" value="Iniciar sesion"/></form></body></html>'
)
_LOGIN_PASSWORD_PAGE_HTML = (
    '<html><body><form id="login-form" method="post" action="login.php">'
    '<input type="hidden" name="return" value="index.php"/>'
    '<input type="hidden" name="csrf_token" value="tok-paso2"/>'
    '<input hidden readonly type="text" name="username" value="testuser"/>'
    '<input id="password" name="password" type="password"/></form></body></html>'
)
# Página autenticada: lo que la distingue de una de login es el link de
# logout en la barra de navegación (marcador positivo de sesión activa).
_LOGGED_IN_HOME_HTML = (
    '<html><body><a href="logout_page.php">Salir</a>'
    "<h1>Bienvenido, testuser</h1></body></html>"
)


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
        # Flujo REAL: usuario -> login_password_page.php, contraseña -> login.php.
        f"{_BASE_URL}/login_password_page.php": _LOGIN_PASSWORD_PAGE_HTML,
        f"{_BASE_URL}/login.php": _LOGGED_IN_HOME_HTML,
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
        f"{_BASE_URL}/login_password_page.php": _LOGIN_PASSWORD_PAGE_HTML,
        # Contraseña incorrecta: Mantis vuelve a servir la página de login
        # (sin link de logout = sesión NO autenticada).
        f"{_BASE_URL}/login.php": _LOGIN_PAGE_HTML,
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
        # Usuario inexistente: Mantis devuelve de nuevo el form de usuario
        # (SIN campo de contraseña) en vez de avanzar al paso 2.
        f"{_BASE_URL}/login_password_page.php": _LOGIN_PAGE_HTML,
    }
    session = _make_session(get_map, post_map)

    adapter = MantisWebScrapingReadAdapter(
        _BASE_URL, [310], "usuario-inexistente", "cualquiera", session=session
    )
    with pytest.raises(MantisScrapingAuthError, match="usuario"):
        adapter.get_session()


# ── Listado parseado correctamente ───────────────────────────────────────


_SET_PROJECT_URL = f"{_BASE_URL}/set_project.php?project_id=310"
_FILTRO_TODOS_URL = (
    f"{_BASE_URL}/view_all_set.php?type=1&project_id[]=310&per_page=500"
    "&hide_status_id=-2&status_id=0"
)
_PAGINA_VACIA_HTML = (
    '<html><body><a href="logout_page.php">Salir</a>'
    "<table><tbody></tbody></table></body></html>"
)


def test_fetch_all_issues_parsea_listado_con_conteo_e_ids():
    list_html = _load_fixture("mantis_view_all_bug_page_sample.html")
    get_map, post_map = _happy_path_login_maps()
    # Fija el filtro "todos los estados" y luego pagina hasta agotar.
    get_map[_SET_PROJECT_URL] = list_html
    get_map[_FILTRO_TODOS_URL] = list_html
    get_map[f"{_BASE_URL}/view_all_bug_page.php?page_number=1"] = list_html
    get_map[f"{_BASE_URL}/view_all_bug_page.php?page_number=2"] = _PAGINA_VACIA_HTML
    session = _make_session(get_map, post_map)

    adapter = MantisWebScrapingReadAdapter(
        _BASE_URL, [310], "testuser", "correcthorsebattery", session=session
    )
    issues = adapter.fetch_all_issues()

    assert len(issues) == 3
    assert [i["id"] for i in issues] == [1001, 1002, 1003]
    assert issues[0]["summary"] == "Fallo al generar reporte mensual de ejemplo"
    # El estado sale del ID numérico de la clase CSS (`status-10-fg`), NO del
    # texto visible ("nueva"): así el mapeo no depende del idioma.
    assert issues[0]["status"] == "new"
    assert issues[1]["status"] == "resolved"
    # La prioridad viaja en el `title` del icono, y en esta instancia está
    # en español.
    assert issues[0]["priority"] == "alta"
    assert issues[1]["priority"] == "normal"
    assert issues[0]["severity"] == "menor"
    assert issues[0]["category"] == "Procesos de Carga"
    assert all(i["project_id"] == 310 for i in issues)


def test_fetch_all_issues_pagina_hasta_agotar_sin_perder_issues():
    """Regresión: el adapter leía SOLO la primera página. Contra el proyecto
    real eso devolvía 11 de 583 issues (el filtro por defecto además ocultaba
    los resueltos). Debe recorrer todas las páginas y deduplicar por ID."""
    pagina1 = _load_fixture("mantis_view_all_bug_page_sample.html")
    pagina2 = pagina1.replace("1001", "2001").replace("1002", "2002").replace("1003", "2003")
    get_map, post_map = _happy_path_login_maps()
    get_map[_SET_PROJECT_URL] = pagina1
    get_map[_FILTRO_TODOS_URL] = pagina1
    get_map[f"{_BASE_URL}/view_all_bug_page.php?page_number=1"] = pagina1
    get_map[f"{_BASE_URL}/view_all_bug_page.php?page_number=2"] = pagina2
    get_map[f"{_BASE_URL}/view_all_bug_page.php?page_number=3"] = _PAGINA_VACIA_HTML
    session = _make_session(get_map, post_map)

    adapter = MantisWebScrapingReadAdapter(
        _BASE_URL, [310], "testuser", "correcthorsebattery", session=session
    )
    issues = adapter.fetch_all_issues()

    assert [i["id"] for i in issues] == [1001, 1002, 1003, 2001, 2002, 2003]


def test_fetch_all_issues_sin_resueltos_no_fuerza_el_filtro():
    """Con `include_resolved_closed=False` se respeta el filtro guardado del
    usuario (no se reescribe su vista por defecto en Mantis)."""
    list_html = _load_fixture("mantis_view_all_bug_page_sample.html")
    get_map, post_map = _happy_path_login_maps()
    get_map[_SET_PROJECT_URL] = list_html
    get_map[f"{_BASE_URL}/view_all_set.php?type=1&project_id[]=310&per_page=500"] = list_html
    get_map[f"{_BASE_URL}/view_all_bug_page.php?page_number=1"] = list_html
    get_map[f"{_BASE_URL}/view_all_bug_page.php?page_number=2"] = _PAGINA_VACIA_HTML
    session = _make_session(get_map, post_map)

    adapter = MantisWebScrapingReadAdapter(
        _BASE_URL, [310], "testuser", "correcthorsebattery",
        session=session, include_resolved_closed=False,
    )

    assert len(adapter.fetch_all_issues()) == 3


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
        if url == f"{_BASE_URL}/login_password_page.php":
            return _FakeResponse(_LOGIN_PASSWORD_PAGE_HTML)
        if url == f"{_BASE_URL}/login.php":
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
        if url == f"{_BASE_URL}/login_password_page.php":
            return _FakeResponse(_LOGIN_PASSWORD_PAGE_HTML)
        if url == f"{_BASE_URL}/login.php":
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


# ── Instancia en ESPAÑOL (regresión: bug hallado contra el Mantis real) ──


_DETALLE_ES_HTML = (
    '<html><body><a href="logout_page.php">Salir</a>'
    '<table class="bug-description-table">'
    '<tr><td class="bug-label">Resumen</td>'
    '<td class="bug-value">Fallo al generar reporte</td></tr>'
    '<tr><td class="bug-label">Descripci&oacute;n</td>'
    '<td class="bug-value">Detalle del problema</td></tr>'
    '<tr><td class="bug-label">Reportador</td>'
    '<td class="bug-value">reportero.demo</td></tr>'
    '<tr><td class="bug-label">Asignado a</td>'
    '<td class="bug-value">dev.demo</td></tr>'
    '<tr><td class="bug-label">Estado</td><td class="bug-value">new</td></tr>'
    '<tr><td class="bug-label">Prioridad</td><td class="bug-value">high</td></tr>'
    '<tr><td class="bug-label">Gravedad</td><td class="bug-value">minor</td></tr>'
    '<tr><td class="bug-label">Categor&iacute;a</td>'
    '<td class="bug-value">General</td></tr>'
    '<tr><td class="bug-label">Pasos para reproducir</td>'
    '<td class="bug-value">1. Abrir 2. Fallar</td></tr>'
    '<tr><td class="bug-label">Informaci&oacute;n adicional</td>'
    '<td class="bug-value">Notas extra</td></tr>'
    "</table></body></html>"
)


def test_detalle_parsea_instancia_en_espanol():
    """Mantis renderiza las etiquetas de `view.php` en el idioma de la
    instancia. La de referencia (soporte.ais-int.net) está en ESPAÑOL: el
    parser original solo miraba claves en inglés y devolvía el detalle
    entero VACÍO contra el servidor real. Los fixtures en inglés no lo
    detectaban porque estaban hechos a medida del parser."""
    get_map, post_map = _happy_path_login_maps()
    get_map[f"{_BASE_URL}/view.php?id=1001"] = _DETALLE_ES_HTML
    session = _make_session(get_map, post_map)

    adapter = MantisWebScrapingReadAdapter(
        _BASE_URL, [310], "testuser", "correcthorsebattery", session=session
    )
    detail = adapter.fetch_issue_detail(1001)

    assert detail["summary"] == "Fallo al generar reporte"
    assert detail["reporter"] == "reportero.demo"
    assert detail["handler"] == "dev.demo"
    assert detail["status"] == "new"
    assert detail["priority"] == "high"
    assert detail["severity"] == "minor"
    assert detail["category"] == "General"
    assert detail["description"] == "Detalle del problema"
    assert detail["steps_to_reproduce"] == "1. Abrir 2. Fallar"
    assert detail["additional_information"] == "Notas extra"


# ── Categoría sin prefijo de proyecto (bug que rompió 42 issues reales) ──


def test_categoria_no_arrastra_el_prefijo_del_proyecto():
    """En la celda de categoría Mantis antepone el proyecto entre corchetes
    (`<span class="small project">[Proyecto]</span>&#160;&#160;Categoría`).
    Si ese prefijo se cuela, el label queda
    `category::[602253 REC Banco…]\xa0\xa0General` y GitLab responde 500 al
    crear el issue: en la migración real así fallaron 42 de 52 issues."""
    fila = (
        '<html><body><a href="logout_page.php">x</a><table><tr>'
        '<td class="column-priority"><i title="normal"></i></td>'
        '<td class="column-id"><a href="/mantis/view.php?id=1001">0001001</a></td>'
        '<td class="column-category"><div class="align-left">'
        '<span class="small project">[<a href="#">602253 REC Proyecto Ejemplo</a>]</span>'
        "&#160;&#160;Procesos de Carga</div></td>"
        '<td class="column-status"><i class="status-10-fg"></i></td>'
        '<td class="column-summary"><a href="view.php?id=1001">Titulo</a></td>'
        "</tr></table></body></html>"
    )
    get_map, post_map = _happy_path_login_maps()
    get_map[_SET_PROJECT_URL] = fila
    get_map[_FILTRO_TODOS_URL] = fila
    get_map[f"{_BASE_URL}/view_all_bug_page.php?page_number=1"] = fila
    get_map[f"{_BASE_URL}/view_all_bug_page.php?page_number=2"] = _PAGINA_VACIA_HTML
    session = _make_session(get_map, post_map)

    adapter = MantisWebScrapingReadAdapter(
        _BASE_URL, [310], "testuser", "correcthorsebattery", session=session
    )
    categoria = adapter.fetch_all_issues()[0]["category"]

    assert categoria == "Procesos de Carga"
    assert "[" not in categoria and "602253" not in categoria
    assert "\xa0" not in categoria, "el espacio duro rompe los labels de GitLab"
