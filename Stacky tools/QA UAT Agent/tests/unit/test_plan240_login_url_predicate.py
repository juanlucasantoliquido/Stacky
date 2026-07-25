"""Tests del fin del falso negativo de login — Plan 240 F1."""
import ast
from pathlib import Path

import auth_session_factory as asf
from auth_session_factory import _is_post_login_url

_TOOL_ROOT = Path(asf.__file__).resolve().parent
_SKIP_DIRS = {"node_modules", "_attic", ".venv", "venv", "playwright-report", "test-results"}


# ── Fakes minimos de Playwright ───────────────────────────────────────────────

class _FakeLocator:
    def __init__(self, page):
        self._page = page

    def click(self, **kw):
        self._page.clicked = True


class _FakePage:
    def __init__(self, final_url, title="", wait_raises=False):
        self.url = final_url
        self._title = title
        self.wait_raises = wait_raises
        self.wait_for_url_arg_type = None
        self.clicked = False

    def goto(self, *a, **kw):
        return None

    def fill(self, *a, **kw):
        return None

    def locator(self, *a, **kw):
        return _FakeLocator(self)

    def wait_for_url(self, arg, **kw):
        self.wait_for_url_arg_type = type(arg)
        if self.wait_raises:
            raise TimeoutError("timeout simulado")

    def wait_for_load_state(self, *a, **kw):
        return None

    def title(self):
        return self._title


class _FakeContext:
    def __init__(self, page):
        self._page = page

    def new_page(self):
        return self._page

    def storage_state(self, path=None):
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text('{"cookies": [{"name": "x"}]}', encoding="utf-8")
        return {}


class _FakeBrowser:
    def __init__(self, page):
        self._page = page

    def new_context(self, **kw):
        return _FakeContext(self._page)

    def close(self):
        return None


class _FakeChromium:
    def __init__(self, page):
        self._page = page

    def launch(self, **kw):
        return _FakeBrowser(self._page)


class _FakePW:
    def __init__(self, page):
        self.chromium = _FakeChromium(page)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _login_with(monkeypatch, page, tmp_path):
    monkeypatch.setattr(
        "playwright.sync_api.sync_playwright", lambda: _FakePW(page), raising=False
    )
    return asf._do_playwright_login(
        "http://localhost:35017/AgendaWeb/", "PABLO", "PABLO",
        tmp_path / "agenda.json", "fp123",
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_predicado_reconoce_frmagenda():
    assert _is_post_login_url("http://h/AgendaWeb/FrmAgenda.aspx") is True
    assert _is_post_login_url("http://h/AgendaWeb/frmLogin.aspx") is False
    assert _is_post_login_url("http://h/AgendaWeb/FRMLOGIN.ASPX") is False


def test_wait_for_url_recibe_callable(monkeypatch, tmp_path):
    """Ratchet del bug: el primer argumento JAMAS puede ser un str (seria glob)."""
    page = _FakePage("http://localhost:35017/AgendaWeb/FrmAgenda.aspx", "Agenda Personal")
    _login_with(monkeypatch, page, tmp_path)
    assert page.wait_for_url_arg_type is not None
    assert page.wait_for_url_arg_type is not str
    assert callable(page.wait_for_url_arg_type) or page.wait_for_url_arg_type.__name__ == "function"


def test_login_ok_devuelve_landing(monkeypatch, tmp_path):
    page = _FakePage("http://localhost:35017/AgendaWeb/FrmAgenda.aspx", "Agenda Personal")
    res = _login_with(monkeypatch, page, tmp_path)
    assert res["ok"] is True
    assert res["reason"] == "AUTH_LOGIN_OK"
    assert "FrmAgenda.aspx" in res["landing_url"]
    assert res["landing_title"] == "Agenda Personal"
    assert res["post_login_matched"] is True


def test_sigue_en_login_es_credenciales_invalidas(monkeypatch, tmp_path):
    page = _FakePage("http://localhost:35017/AgendaWeb/frmLogin.aspx", "Login")
    res = _login_with(monkeypatch, page, tmp_path)
    assert res["ok"] is False
    assert res["reason"] == "AUTH_CREDENTIALS_INVALID"


def test_aterrizaje_desconocido_no_es_credenciales(monkeypatch, tmp_path):
    page = _FakePage("http://localhost:35017/AgendaWeb/FrmOtra.aspx", "Otra",
                     wait_raises=True)
    res = _login_with(monkeypatch, page, tmp_path)
    assert res["ok"] is False
    assert res["reason"] == "AUTH_POST_LOGIN_UNRECOGNIZED"


def test_ratchet_ningun_wait_for_url_con_string_literal():
    """Escaneo por AST (jamas por regex) de todos los .py del tool."""
    offenders, skipped = [], []
    for py in _TOOL_ROOT.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in py.parts):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            skipped.append(py.name)
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = getattr(fn, "attr", None) or getattr(fn, "id", None)
            if name != "wait_for_url" or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                offenders.append(f"{py.name}:{node.lineno}")
    if skipped:
        print(f"[ratchet] archivos no parseables (informativo): {skipped}")
    assert offenders == [], f"wait_for_url con string literal (seria glob): {offenders}"
