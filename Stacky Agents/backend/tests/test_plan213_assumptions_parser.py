"""Plan 213 F0 — Parser de supuestos: determinista, tolerante y que nunca lanza."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import assumptions as A  # noqa: E402
from services.intent_preflight import IntentAssumption  # noqa: E402


def test_parse_full_form():
    r = A.parse("[SUPUESTO: el tope es 100 | base: doc funcional M12 | impacto: bajo]")

    assert len(r.assumptions) == 1
    assert r.assumptions[0].impact == "low"
    assert r.assumptions[0].basis == "doc funcional M12"


def test_parse_minimal_form_is_high_impact():
    """Sin base declarada, el supuesto obliga a confirmación humana."""
    r = A.parse("[SUPUESTO: el cliente usa Oracle]")

    a = r.assumptions[0]
    assert a.impact == "high"
    assert a.basis == ""
    assert a.needs_confirmation is True


def test_parse_with_basis_defaults_medium():
    r = A.parse("[SUPUESTO: X | base: tabla RTABL]")

    assert r.assumptions[0].impact == "medium"
    assert r.assumptions[0].needs_confirmation is False


def test_parse_normalizes_spanish_impact():
    r = A.parse("[SUPUESTO: a | impacto: alto]\n"
                "[SUPUESTO: b | impacto: medio]\n"
                "[SUPUESTO: c | impacto: bajo]")

    assert [x.impact for x in r.assumptions] == ["high", "medium", "low"]


def test_parse_is_case_insensitive():
    r = A.parse("[supuesto: x | Base: y | IMPACTO: Alto]")

    assert len(r.assumptions) == 1
    assert r.assumptions[0].impact == "high"
    assert r.assumptions[0].basis == "y"


def test_parse_from_html():
    """Caso crítico: el Analista Técnico publica comment.html, no texto plano."""
    r = A.parse("<p>[SUPUESTO: el batch corre de noche | base: cron RECBATCH]</p>")

    assert len(r.assumptions) == 1, "sin normalizar HTML el parser no ve nada del Técnico"
    assert r.assumptions[0].basis == "cron RECBATCH"


def test_parse_dedupes():
    r = A.parse("[SUPUESTO: mismo] y otra vez [SUPUESTO: MISMO]")

    assert len(r.assumptions) == 1


def test_parse_orders_high_first():
    r = A.parse("[SUPUESTO: b | base: x | impacto: bajo]\n[SUPUESTO: a]")

    assert r.assumptions[0].impact == "high"
    assert r.assumptions[0].text == "a"


def test_parse_pending():
    r = A.parse("[PENDIENTE: monto tope | necesito: valor de negocio]")

    assert len(r.pending) == 1
    assert r.pending[0]["needs"] == "valor de negocio"
    assert r.marks_ok is True


def test_parse_empty_and_none():
    for entrada in ("", None):
        r = A.parse(entrada)
        assert r.assumptions == ()
        assert r.marks_ok is False
        assert r.blocked_without_pending is False


def test_overload_flag(monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_ASSUMPTION_MAX_PER_RUN", 10, raising=False)
    texto = "\n".join(f"[SUPUESTO: supuesto numero {i}]" for i in range(11))

    assert A.parse(texto).overload is True


def test_unbased_count():
    r = A.parse("[SUPUESTO: a | base: x]\n[SUPUESTO: b]\n[SUPUESTO: c]")

    assert r.unbased_count == 2


def test_truncates_giant_assumption():
    """Un supuesto desbordado no puede inflar la metadata ni el panel."""
    r = A.parse(f"[SUPUESTO: {'x' * 5000} | base: {'y' * 1000}]")

    a = r.assumptions[0]
    assert len(a.text) == A.TEXT_MAX and a.text.endswith("…")
    assert len(a.basis) == A.BASIS_MAX and a.basis.endswith("…")


def test_blocked_without_pending_detection():
    frenado = "❓ CONSULTA TÉCNICA (pre-bloqueo): no sé el tope"
    assert A.parse(frenado).blocked_without_pending is True

    honesto = frenado + "\n[PENDIENTE: tope | necesito: valor]"
    assert A.parse(honesto).blocked_without_pending is False


def test_strip_canonical_marks():
    limpio = A.strip_canonical_marks("x [SUPUESTO: a | base: b] y [PENDIENTE: c]")

    assert "SUPUESTO" not in limpio and "PENDIENTE" not in limpio
    assert "x" in limpio and "y" in limpio


def test_intent_assumption_basis_is_backward_compatible():
    a = IntentAssumption(text="x", impact="high", needs_confirmation=True)

    assert a.basis == ""


def test_to_metadata_shape():
    r = A.parse("[SUPUESTO: a | base: b | impacto: bajo]\n[PENDIENTE: c | necesito: d]")
    meta = A.to_metadata(r)

    assert meta["assumptions"]["total"] == 1
    assert meta["assumptions"]["items"][0]["basis"] == "b"
    assert meta["assumptions"]["pending"][0]["needs"] == "d"
    assert meta["assumptions"]["marks_ok"] is True
    assert meta["assumptions"]["items"][0]["status"] == "pending", \
        "un agente no se autoconfirma sus supuestos"
