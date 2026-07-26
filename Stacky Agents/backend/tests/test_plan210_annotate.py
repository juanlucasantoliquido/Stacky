"""Plan 210 F5 — El bloque BUILD que llega a ADO es el veredicto de MÁQUINA.

Un verde narrado por el LLM sin respaldo queda tachado; el bloque autoritativo
dice la verdad con la razón exacta.
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

_ADO = 210900
_WS = "C:\\ws"

_HTML_VERDE = (
    "<h1>Entregable</h1><h2>3. BUILD</h2>"
    '<p><span style="color:green"><strong>✓ Build OK</strong></span> — compiló todo</p>'
    "<hr><h2>4. OTRA</h2><p>fin</p>"
)


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    dbv._EVIDENCE_CONTRIBUTORS.clear()
    monkeypatch.setattr(dbv, "write_verdict", lambda *a, **kw: None, raising=True)


def _verdict(monkeypatch, **kw):
    base = {"ok": True, "gate_ok": True, "entry_kind": "sln", "reason": "ok",
            "solution": "App.sln", "returncode": 0, "execution_id": 5,
            "toolchain": {"available": True, "builder": "dotnet", "version": "8"}}
    base.update(kw)
    v = dbv.BuildVerdict(**base)
    monkeypatch.setattr(dbv, "read_verdict", lambda a, w: v, raising=True)
    return v


def _anotar(html=_HTML_VERDE, agent_type="developer"):
    return dbv.annotate_build_evidence(ado_id=_ADO, agent_type=agent_type,
                                       workspace_root=_WS, html=html)


def test_passthrough_non_developer(monkeypatch):
    _verdict(monkeypatch, gate_ok=False, ok=False, reason="build_failed")

    assert _anotar(agent_type="technical") == _HTML_VERDE


def test_passthrough_flag_off(monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_DEV_BUILD_VERIFY_ENABLED", False, raising=False)
    _verdict(monkeypatch, gate_ok=False, ok=False)

    assert _anotar() == _HTML_VERDE


def test_ok_verdict_inserts_green_authoritative_block(monkeypatch):
    _verdict(monkeypatch, gate_ok=True, ok=True, reason="ok")

    out = _anotar()

    assert "Build OK (verificado por máquina)" in out
    assert "color:green" in out
    assert "App.sln" in out
    assert dbv._MARKER in out
    assert "4. OTRA" in out, "el resto del deliverable se conserva"


def test_no_verdict_neutralizes_llm_green(monkeypatch):
    monkeypatch.setattr(dbv, "read_verdict", lambda a, w: None, raising=True)

    out = _anotar()

    assert "✗ Build NO verificado" in out
    assert "Ninguna máquina verificó este build" in out
    assert "<strong>✓ Build OK</strong>" not in out, "el verde del LLM se neutraliza"


def test_build_failed_shows_red_reason(monkeypatch):
    _verdict(monkeypatch, gate_ok=False, ok=False, reason="build_failed")

    out = _anotar()

    assert "color:red" in out
    assert "La compilación devolvió errores" in out


def test_no_sln_muestra_razon_legible(monkeypatch):
    _verdict(monkeypatch, gate_ok=False, ok=False, reason="no_sln", entry_kind="none")

    assert "No se encontró ninguna solución .sln" in _anotar()


def test_plain_text_build_ok_is_struck(monkeypatch):
    """El seed del prompt vive en el RESUMEN, fuera de la sección BUILD: ahí el
    claim en texto plano tiene que quedar tachado igual."""
    monkeypatch.setattr(dbv, "read_verdict", lambda a, w: None, raising=True)
    html = ("<h2>RESUMEN RÁPIDO</h2><p>Implementé la validación. ✓ Build OK</p>"
            "<h2>3. BUILD</h2><p>detalle</p>")

    out = _anotar(html)

    assert "Build OK (no verificado)" in out
    assert "<s>" in out
    assert "✓ Build OK</p>" not in out


def test_claim_dentro_de_la_seccion_se_reemplaza_por_la_verdad(monkeypatch):
    monkeypatch.setattr(dbv, "read_verdict", lambda a, w: None, raising=True)

    out = _anotar()

    assert "✓ Build OK" not in out
    assert "✗ Build NO verificado" in out


def test_idempotent_double_annotation(monkeypatch):
    _verdict(monkeypatch, gate_ok=True, ok=True)

    una = _anotar()
    dos = dbv.annotate_build_evidence(ado_id=_ADO, agent_type="developer",
                                      workspace_root=_WS, html=una)

    assert una == dos
    assert una.count(dbv._MARKER) == 1


def test_sin_seccion_build_anexa_el_bloque(monkeypatch):
    _verdict(monkeypatch, gate_ok=True, ok=True)

    out = _anotar("<h1>Entregable sin seccion build</h1>")

    assert dbv._MARKER in out
    assert "Entregable sin seccion build" in out


def test_contributor_findings_flip_gate_and_persist(monkeypatch):
    v = _verdict(monkeypatch, gate_ok=True, ok=True, reason="ok", execution_id=77)
    persistidos: list = []
    monkeypatch.setattr(dbv, "write_verdict",
                        lambda a, w, verdict: persistidos.append(verdict), raising=True)

    dbv.register_evidence_contributor(lambda ado_id, verdict: {
        "section_html": "<p>hallazgo del inspector</p>",
        "blocking": [{"kind": "residuo", "severity": "blocking", "file": "x.cs",
                      "detail": "cadena de otro cliente"}],
    })

    out = _anotar()

    assert persistidos, "el veredicto fusionado se re-persiste para que el gate lo lea"
    fusionado = persistidos[-1]
    assert fusionado.gate_ok is False, "un finding bloqueante voltea el gate"
    assert len(fusionado.blocking_findings) == 1
    assert fusionado.execution_id == 77, "el replace preserva la corrida"
    assert fusionado.verified_at == v.verified_at
    assert "hallazgo del inspector" in out
    assert "✗ Build NO verificado" in out


def test_contributor_que_lanza_no_rompe(monkeypatch):
    _verdict(monkeypatch, gate_ok=True, ok=True)

    def _boom(ado_id, verdict):
        raise RuntimeError("inspector roto")

    dbv.register_evidence_contributor(_boom)

    out = _anotar()

    assert "Build OK (verificado por máquina)" in out


def test_annotate_nunca_lanza(monkeypatch):
    def _boom(a, w):
        raise RuntimeError("disco roto")

    monkeypatch.setattr(dbv, "read_verdict", _boom, raising=True)

    assert _anotar() == _HTML_VERDE, "ante un error se publica el original"
