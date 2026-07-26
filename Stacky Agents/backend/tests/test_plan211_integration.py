"""Plan 211 F4 — Integración con el gate del 210.

Cierra el falso verde compuesto: "compila, pero quedó un residuo de otro cliente".
Un hallazgo bloqueante baja el gate_ok del veredicto re-persistido, y el gate de
estado del 210 lo lee ⇒ el developer no avanza.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import dev_build_verify as dbv  # noqa: E402

_ADO = 211900

_HTML = "<h1>Entregable</h1><h2>3. BUILD</h2><p>detalle</p>"


@pytest.fixture(autouse=True)
def _limpio(tmp_path, monkeypatch):
    dbv._EVIDENCE_CONTRIBUTORS.clear()
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_DEV_BUILD_VERIFY_ENABLED", True, raising=False)
    yield
    dbv._EVIDENCE_CONTRIBUTORS.clear()


def _sembrar_verdict_ok(ws):
    v = dbv.BuildVerdict(
        ok=True, gate_ok=True, entry_kind="sln", solution="App.sln",
        solutions=("App.sln",), returncode=0, reason="ok",
        toolchain={"available": True, "builder": "dotnet", "version": "8"},
        build_id="b1", verified_at="2026-07-25T00:00:00Z", execution_id=42,
    )
    dbv.write_verdict(_ADO, str(ws), v)
    return v


def _anotar(ws):
    return dbv.annotate_build_evidence(ado_id=_ADO, agent_type="developer",
                                       workspace_root=str(ws), html=_HTML)


def test_blocking_residue_flips_gate_ok_false(tmp_path):
    _sembrar_verdict_ok(tmp_path)
    dbv.register_evidence_contributor(lambda ado_id, verdict: {
        "title": "Residuos de port entre clientes",
        "section_html": "<table><tr><td>dbripley01</td></tr></table>",
        "blocking": [{"kind": "server", "severity": "blocking", "file": "web.config",
                      "detail": "token 'dbripley01' de ripley (server)"}],
        "warnings": [],
    })

    html = _anotar(tmp_path)
    persistido = dbv.read_verdict(_ADO, str(tmp_path))

    assert persistido.gate_ok is False, "un residuo bloqueante baja el Build OK"
    assert len(persistido.blocking_findings) == 1
    assert persistido.execution_id == 42, "la corrida se preserva al fusionar"
    assert "✗ Build NO verificado" in html
    assert "dbripley01" in html


def test_warning_only_keeps_gate_ok_true(tmp_path):
    _sembrar_verdict_ok(tmp_path)
    dbv.register_evidence_contributor(lambda ado_id, verdict: {
        "title": "Residuos de port entre clientes",
        "section_html": "<table><tr><td>aviso</td></tr></table>",
        "blocking": [],
        "warnings": [{"kind": "product", "severity": "warning", "file": "a.cs",
                      "detail": "token 'rsripley' de ripley (product)"}],
    })

    html = _anotar(tmp_path)
    persistido = dbv.read_verdict(_ADO, str(tmp_path))

    assert persistido.gate_ok is True, "un warning NO baja el gate"
    assert len(persistido.warnings) == 1
    assert "Build OK (verificado por máquina)" in html
    assert "aviso" in html


def test_deliverable_html_lists_findings(tmp_path):
    _sembrar_verdict_ok(tmp_path)
    dbv.register_evidence_contributor(lambda ado_id, verdict: {
        "title": "Inspección post-build",
        "section_html": "<h3>Inspección post-build</h3><table><tr><td>App.csproj</td></tr></table>",
        "blocking": [{"kind": "post_build_event", "severity": "blocking",
                      "file": "App.csproj", "detail": "copia a otro cliente"}],
        "warnings": [],
    })

    html = _anotar(tmp_path)

    assert "Inspección post-build" in html
    assert "App.csproj" in html


def test_gate_de_estado_ve_el_downgrade(tmp_path, monkeypatch):
    """El gate de estado lee el veredicto RE-PERSISTIDO: el developer no avanza."""
    from services import client_profile

    monkeypatch.setattr(
        client_profile, "load_effective_client_profile",
        lambda p: {"tracker_state_machine": {"developer": {
            "input_states": ["Ready for Dev"], "next_state_ok": "Reviewed by Dev"}}},
        raising=True,
    )
    _sembrar_verdict_ok(tmp_path)
    dbv.register_evidence_contributor(lambda ado_id, verdict: {
        "title": "t", "section_html": "",
        "blocking": [{"kind": "server", "severity": "blocking", "file": "f",
                      "detail": "residuo"}],
        "warnings": [],
    })
    _anotar(tmp_path)

    estado, meta = dbv.gate_final_state(
        project_name="pacifico", agent_type="developer", ado_id=_ADO,
        workspace_root=str(tmp_path), proposed_state="Reviewed by Dev", execution_id=42,
    )

    assert estado == "Ready for Dev", "el ticket queda en revisión, no avanza"
    assert meta["gate_ok"] is False


def test_dos_contribuidores_acumulan(tmp_path):
    _sembrar_verdict_ok(tmp_path)
    dbv.register_evidence_contributor(lambda a, v: {
        "title": "A", "section_html": "<p>A</p>",
        "blocking": [{"kind": "x", "severity": "blocking", "file": "1", "detail": "d1"}],
        "warnings": [],
    })
    dbv.register_evidence_contributor(lambda a, v: {
        "title": "B", "section_html": "<p>B</p>",
        "blocking": [{"kind": "y", "severity": "blocking", "file": "2", "detail": "d2"}],
        "warnings": [],
    })

    html = _anotar(tmp_path)
    persistido = dbv.read_verdict(_ADO, str(tmp_path))

    assert len(persistido.blocking_findings) == 2
    assert "<p>A</p>" in html and "<p>B</p>" in html
