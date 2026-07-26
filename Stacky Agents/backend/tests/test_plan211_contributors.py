"""Plan 211 F3 — Contribuidores enchufados a la seam de evidencia del gate."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import dev_build_contributors as dbc  # noqa: E402


class _Verdict:
    def __init__(self, solutions=("C:\\ws\\App.sln",)):
        self.solutions = tuple(solutions)


@pytest.fixture(autouse=True)
def _entorno(monkeypatch):
    from config import config as cfg
    from services import dev_build_verify, port_residue_scanner

    monkeypatch.setattr(cfg, "STACKY_DEV_POST_BUILD_INSPECT_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg, "STACKY_DEV_PORT_RESIDUE_SCAN_ENABLED", True, raising=False)
    monkeypatch.setattr(dev_build_verify, "project_name_for_ado", lambda a: "pacifico",
                        raising=True)
    monkeypatch.setattr(dev_build_verify, "workspace_root_for_ado", lambda a: "C:\\ws",
                        raising=True)
    monkeypatch.setattr(port_residue_scanner, "build_foreign_token_catalog",
                        lambda p: {"ripley": {"source_project": "ripley", "kind": "workspace"}},
                        raising=True)
    monkeypatch.setattr(port_residue_scanner, "allowlist_for_project", lambda p: [],
                        raising=True)
    monkeypatch.setattr(port_residue_scanner, "changed_files", lambda ws: [], raising=True)
    monkeypatch.setattr(port_residue_scanner, "scan_files_for_foreign_tokens",
                        lambda *a, **kw: [], raising=True)
    monkeypatch.setattr(dbc, "_project_files_for_solutions", lambda s, ws: list(s),
                        raising=True)
    dbc._REGISTERED = False
    yield
    dbc._REGISTERED = False


def test_inspect_contributor_off_returns_empty(monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_DEV_POST_BUILD_INSPECT_ENABLED", False, raising=False)

    assert dbc._inspect_contributor(1, _Verdict())["blocking"] == []
    assert dbc._inspect_contributor(1, _Verdict())["section_html"] == ""


def test_residue_contributor_off_returns_empty(monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_DEV_PORT_RESIDUE_SCAN_ENABLED", False, raising=False)

    assert dbc._residue_contributor(1, _Verdict()) == dbc._empty()


def test_inspect_skips_when_no_solutions():
    assert dbc._inspect_contributor(1, _Verdict(solutions=())) == dbc._empty()


def test_catalog_scoped_to_ticket_project(monkeypatch):
    from services import port_residue_scanner

    recibidos: list = []
    monkeypatch.setattr(port_residue_scanner, "build_foreign_token_catalog",
                        lambda p: recibidos.append(p) or {}, raising=True)

    dbc._residue_contributor(1, _Verdict())

    assert recibidos == ["pacifico"], "el catálogo excluye el proyecto DEL TICKET, no el activo"


def test_residue_passes_allowlist(monkeypatch):
    from services import port_residue_scanner

    recibidos: list = []
    monkeypatch.setattr(port_residue_scanner, "allowlist_for_project", lambda p: ["x"],
                        raising=True)
    monkeypatch.setattr(port_residue_scanner, "scan_files_for_foreign_tokens",
                        lambda *a, **kw: recibidos.append(kw) or [], raising=True)

    dbc._residue_contributor(1, _Verdict())

    assert recibidos[0]["allowlist"] == ["x"]


def test_contribution_shape(monkeypatch):
    from services import post_build_inspector

    monkeypatch.setattr(post_build_inspector, "inspect_projects", lambda *a, **kw: [],
                        raising=True)

    out = dbc._inspect_contributor(1, _Verdict())

    assert set(out.keys()) == {"title", "section_html", "blocking", "warnings"}


def test_blocking_finding_present_in_contribution(monkeypatch):
    from services import post_build_inspector

    monkeypatch.setattr(
        post_build_inspector, "inspect_projects",
        lambda *a, **kw: [post_build_inspector.InspectFinding(
            "post_build_event", "blocking", "App.csproj", "copia a otro cliente", "xcopy")],
        raising=True,
    )

    out = dbc._inspect_contributor(1, _Verdict())

    assert len(out["blocking"]) == 1
    assert out["blocking"][0]["severity"] == "blocking"
    assert "copia a otro cliente" in out["section_html"]
    assert "Inspección post-build" in out["title"]


def test_section_html_escapa_contenido(monkeypatch):
    from services import post_build_inspector

    monkeypatch.setattr(
        post_build_inspector, "inspect_projects",
        lambda *a, **kw: [post_build_inspector.InspectFinding(
            "copy_task", "warning", "<script>x</script>", "detalle & raro", "e")],
        raising=True,
    )

    html = dbc._inspect_contributor(1, _Verdict())["section_html"]

    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&amp;" in html


def test_register_calls_register_fn_twice():
    capturados: list = []

    dbc.register(capturados.append)

    assert len(capturados) == 2
    assert dbc._inspect_contributor in capturados
    assert dbc._residue_contributor in capturados


def test_register_is_idempotent():
    capturados: list = []

    dbc.register(capturados.append)
    dbc.register(capturados.append)

    assert len(capturados) == 2, "registrar dos veces duplicaría los findings"


def test_contribuidor_que_falla_devuelve_vacio(monkeypatch):
    from services import post_build_inspector

    def _boom(*a, **kw):
        raise RuntimeError("inspector roto")

    monkeypatch.setattr(post_build_inspector, "inspect_projects", _boom, raising=True)

    assert dbc._inspect_contributor(1, _Verdict()) == dbc._empty()
