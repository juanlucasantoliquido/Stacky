"""Plan 213 F1 — Dejar de castigar la honestidad, sin dejar de detectar el abuso.

El sistema restaba 8 puntos por cada "[PENDIENTE" y por cada "asumo que": un
analista que declaraba sus supuestos terminaba en needs_review, o sea frenado
igual. Acá se separa el supuesto DECLARADO (rigor) del hedge vago (evasión).
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

import contract_validator  # noqa: E402
from services import confidence  # noqa: E402

_KEY = "STACKY_ASSUMPTION_MODE_ENABLED"

# Cuerpo largo para pasar el mínimo de palabras del scoring por sección.
_CUERPO = " ".join(["analisis del proceso batch de recobro"] * 40)


@pytest.fixture
def modo_on(monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, _KEY, True, raising=False)
    return cfg


def _score(texto: str) -> int:
    return confidence._score_section(texto)[0]


def test_canonical_assumption_does_not_lower_confidence(modo_on):
    """KPI-6: declarar supuestos con base no puede costar puntos."""
    sin = _CUERPO
    con = (
        _CUERPO
        + "\n[SUPUESTO: el batch corre de noche | base: cron RECBATCH | impacto: bajo]"
        + "\n[SUPUESTO: el tope es 100 | base: doc M12 | impacto: bajo]"
        + "\n[SUPUESTO: la tabla es RTABL | base: esquema | impacto: bajo]"
    )

    assert _score(con) >= _score(sin)


def test_vague_hedge_still_penalized(modo_on):
    """El hedge suelto en prosa sigue costando: no se legaliza la vaguedad."""
    limpio = _score(_CUERPO)
    vago = _score(_CUERPO + "\nasumo que el proceso corre de noche")

    assert vago < limpio


def test_pendiente_canonico_not_penalized(modo_on):
    """'[PENDIENTE' está en _HEDGE_PHRASES: el marcador canónico se exime."""
    limpio = _score(_CUERPO)
    canonico = _score(_CUERPO + "\n[PENDIENTE: monto tope | necesito: valor de negocio]")

    assert canonico >= limpio


def test_assumption_discipline_bonus(modo_on):
    _puntos, señales = confidence._score_section(
        _CUERPO + "\n[SUPUESTO: x | base: doc funcional M12 | impacto: bajo]"
    )

    assert "assumption_discipline" in señales


def test_flag_off_scoring_is_identical(monkeypatch):
    """KPI-7: con la flag apagada el score es el de siempre, al punto."""
    from config import config as cfg

    monkeypatch.setattr(cfg, _KEY, False, raising=False)
    texto = _CUERPO + "\n[PENDIENTE: x | necesito: y]\n[SUPUESTO: a | base: b]"

    puntos, señales = confidence._score_section(texto)

    assert any(s.startswith("hedge:[PENDIENTE") for s in señales), \
        "con la flag OFF el marcador sigue penalizando (comportamiento pre-213)"
    assert "assumption_discipline" not in señales
    assert puntos == confidence._score_section(texto)[0]


# ---------------------------------------------------------------------------
# Contrato: warnings visibles, nunca failures
# ---------------------------------------------------------------------------

_EVASIVO = (
    "## Traducción funcional\ncontenido\n## Alcance de cambios\ncontenido\n"
    "## Plan de pruebas\ncontenido\n## Tests unitarios\nTU-001\n"
    "## Notas para el desarrollador\nADO-1234\nno puedo determinar el tope\n"
) + _CUERPO


def _warnings(res) -> list[str]:
    return [w.rule for w in res.warnings]


def test_contract_warns_when_evasion_without_marks(modo_on):
    res = contract_validator.validate("technical", _EVASIVO)

    assert "assumption_missing" in _warnings(res)


def test_contract_no_warning_when_marks_present(modo_on):
    res = contract_validator.validate(
        "technical", _EVASIVO + "\n[SUPUESTO: el tope es 100 | base: doc M12]")

    assert "assumption_missing" not in _warnings(res)


def test_contract_warns_on_unbased(modo_on):
    res = contract_validator.validate(
        "technical", _EVASIVO + "\n[SUPUESTO: a]\n[SUPUESTO: b]")

    unbased = [w for w in res.warnings if w.rule == "assumption_unbased"]
    assert len(unbased) == 1
    assert "2 supuesto" in unbased[0].message


def test_contract_never_fails_on_assumptions(modo_on):
    for texto in (_EVASIVO,
                  _EVASIVO + "\n[SUPUESTO: a]\n[SUPUESTO: b]",
                  _EVASIVO + "\n" + "\n".join(f"[SUPUESTO: s{i}]" for i in range(12))):
        res = contract_validator.validate("technical", texto)
        reglas = [f.rule for f in res.failures]
        assert not any(r.startswith("assumption_") for r in reglas), reglas


def test_contract_flag_off_adds_no_warnings(monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, _KEY, False, raising=False)

    res = contract_validator.validate("technical", _EVASIVO)

    assert not any(r.startswith("assumption_") for r in _warnings(res))


def test_developer_contract_untouched():
    """G6: el Developer no declara supuestos, construye. Protege al plan 210."""
    assert "assumption_discipline" not in contract_validator._CONTRACTS["developer"]
    assert contract_validator._CONTRACTS["functional"]["assumption_discipline"] is True
    assert contract_validator._CONTRACTS["technical"]["assumption_discipline"] is True
