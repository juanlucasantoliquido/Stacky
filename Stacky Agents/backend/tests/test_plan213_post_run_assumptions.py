"""Plan 213 F4 — Los supuestos quedan persistidos en los TRES runtimes.

No hay chokepoint único post-run: codex pasa por finalize_run, claude corre su
bloque de calidad inline y copilot lo hace en agent_runner. Por eso la lógica
vive en UN helper y hay tres call-sites; el grep-gate de abajo lo custodia.
"""
from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import assumptions as A  # noqa: E402

_KEY = "STACKY_ASSUMPTION_MODE_ENABLED"
_TYPES = "STACKY_ASSUMPTION_MODE_AGENT_TYPES"


@pytest.fixture
def modo_on(monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, _KEY, True, raising=False)
    monkeypatch.setattr(cfg, _TYPES, "technical,functional", raising=False)
    monkeypatch.setattr(cfg, "STACKY_ASSUMPTION_MAX_PER_RUN", 10, raising=False)
    return cfg


_DOS = "[SUPUESTO: a | base: doc M12]\n[SUPUESTO: b | base: tabla RTABL]"


def test_apply_adds_assumptions_for_technical(modo_on):
    meta: dict = {}

    assert A.apply_to_metadata("technical", _DOS, meta) is None
    assert meta["assumptions"]["total"] == 2


def test_apply_adds_empty_assumptions_when_none(modo_on):
    """KPI-2: la clave existe siempre, aunque el análisis no haya asumido nada."""
    meta: dict = {}

    A.apply_to_metadata("functional", "un analisis sin supuestos", meta)

    assert meta["assumptions"]["total"] == 0
    assert meta["assumptions"]["marks_ok"] is False


def test_apply_skips_for_developer(modo_on):
    """G6: el Developer no declara supuestos. Protege el gate del plan 210."""
    meta: dict = {}

    assert A.apply_to_metadata("developer", _DOS, meta) is None
    assert "assumptions" not in meta


def test_apply_parses_html_output(modo_on):
    meta: dict = {}

    A.apply_to_metadata("technical", "<p>[SUPUESTO: x | base: y]</p>", meta)

    assert meta["assumptions"]["total"] == 1


def test_apply_overload_returns_needs_review(modo_on):
    meta: dict = {}
    texto = "\n".join(f"[SUPUESTO: numero {i}]" for i in range(11))

    assert A.apply_to_metadata("technical", texto, meta) == "needs_review"


def test_apply_never_raises(monkeypatch, modo_on):
    def _boom(_texto):
        raise RuntimeError("parser roto")

    monkeypatch.setattr(A, "parse", _boom)
    meta = {"contract_score": 90}
    avisos: list[tuple] = []

    assert A.apply_to_metadata("technical", _DOS, meta,
                               log=lambda n, m: avisos.append((n, m))) is None
    assert meta == {"contract_score": 90}, "la metadata ajena queda intacta"
    assert avisos and avisos[0][0] == "warn"


def test_apply_flag_off_is_noop(monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, _TYPES, "", raising=False)
    meta: dict = {}

    assert A.apply_to_metadata("technical", _DOS, meta) is None
    assert meta == {}


def test_metadata_patch_preserves_foreign_keys(modo_on):
    """Convivencia con los planes 210/211: se fusiona, nunca se reasigna."""
    meta = {"contract_score": 88, "build_verdict": {"gate_ok": True}}

    A.apply_to_metadata("technical", _DOS, meta)

    assert meta["contract_score"] == 88
    assert meta["build_verdict"]["gate_ok"] is True
    assert meta["assumptions"]["total"] == 2


def test_metadata_roundtrips_as_json_string(modo_on):
    """metadata_json es una columna Text: el shape tiene que sobrevivir el dumps."""
    meta: dict = {}
    A.apply_to_metadata("technical", _DOS + "\n[PENDIENTE: tope | necesito: valor]", meta)

    ida_y_vuelta = json.loads(json.dumps(meta, ensure_ascii=False))

    assert ida_y_vuelta["assumptions"]["total"] == 2
    assert ida_y_vuelta["assumptions"]["pending"][0]["needs"] == "valor"


# ---------------------------------------------------------------------------
# Los 3 call-sites
# ---------------------------------------------------------------------------

def test_finalize_run_persists_assumptions(modo_on):
    """Call-site codex."""
    from harness.post_run import finalize_run

    res = finalize_run(
        runtime="codex_cli", agent_type="technical",
        output_text="## Traducción funcional\n" + _DOS, ado_id=None,
        gate_enabled=False,
    )

    assert res.metadata_patch["assumptions"]["total"] == 2


def test_finalize_run_overload_suggests_needs_review(modo_on):
    from harness.post_run import finalize_run

    texto = "\n".join(f"[SUPUESTO: numero {i}]" for i in range(11))
    res = finalize_run(runtime="codex_cli", agent_type="technical",
                       output_text=texto, ado_id=None, gate_enabled=False)

    assert res.status_suggestion == "needs_review"


def _llamadas_a(archivo: str) -> list:
    arbol = ast.parse((ROOT / archivo).read_text(encoding="utf-8"))
    return [
        n for n in ast.walk(arbol)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id == "_assump_apply"
    ]


def test_claude_inline_path_persists_assumptions():
    """Call-site claude: se verifica por AST porque vive en un bloque inline."""
    assert _llamadas_a("services/claude_code_cli_runner.py"), \
        "el path de claude quedó sin persistir supuestos"


def test_agent_runner_persists_assumptions():
    """Call-site copilot."""
    assert _llamadas_a("agent_runner.py"), \
        "el path de copilot quedó sin persistir supuestos"


def test_exactly_three_call_sites():
    """Menos de 3 = un runtime sin persistencia = KPI-2 roto, en silencio."""
    archivos = [
        "harness/post_run.py",
        "services/claude_code_cli_runner.py",
        "agent_runner.py",
    ]

    faltantes = [a for a in archivos if not _llamadas_a(a)]

    assert not faltantes, f"runtimes sin persistencia de supuestos: {faltantes}"
