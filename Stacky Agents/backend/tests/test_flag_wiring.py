"""Plan 85 — Centinela de cableado: ninguna flag placebo silenciosa.

Regla: toda key de FLAG_REGISTRY debe aparecer como literal en código
productivo fuera del registry, O estar declarada reserved=True (fase
diferida) con razón. Lista de reservadas CONGELADA: agregar una reservada
nueva exige editar este test a propósito (patrón Plan 61/63).
"""
from pathlib import Path
import pytest

from services.harness_flags import FLAG_REGISTRY

BACKEND_ROOT = Path(__file__).resolve().parent.parent          # .../backend
FRONTEND_SRC = BACKEND_ROOT.parent / "frontend" / "src"        # .../frontend/src

# Lista CONGELADA (Plan 85). Cambiarla es una decisión consciente con code review.
RESERVED_KEYS = frozenset({
    "STACKY_RUN_ADVISOR_ENFORCE",
    "STACKY_BUDGET_PER_TICKET_USD",
    "STACKY_BRIEF_MODEL_SELECT_ENABLED",
    "STACKY_SPECULATIVE_MODE",
})

def _production_corpus() -> str:
    """Concatena el código productivo donde un consumo cuenta como real.

    Incluye: backend/**/*.py y frontend/src/**/*.{ts,tsx}.
    Excluye: backend/tests/** (los tests no son consumo),
             backend/services/harness_flags.py (el registry se define ahí),
             backend/services/harness_flags_help.py (Plan 86: ayuda UI, no consumo lógico).
    NOTA: harness_profiles.py y config.py SÍ cuentan (baseline de la
    auditoría 2026-07-02; endurecerlo es fuera de scope, sección 6).
    """
    parts: list[str] = []
    for path in sorted(BACKEND_ROOT.rglob("*.py")):
        rel = path.relative_to(BACKEND_ROOT).as_posix()
        if rel.startswith("tests/") or rel in ("services/harness_flags.py", "services/harness_flags_help.py"):
            continue
        parts.append(path.read_text(encoding="utf-8", errors="ignore"))
    if FRONTEND_SRC.exists():
        for pattern in ("*.ts", "*.tsx"):
            for path in sorted(FRONTEND_SRC.rglob(pattern)):
                if "__tests__" in path.parts:
                    continue
                parts.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(parts)

@pytest.fixture(scope="module")
def corpus() -> str:
    return _production_corpus()

def test_every_non_reserved_flag_is_wired(corpus):
    dead = [
        spec.key for spec in FLAG_REGISTRY
        if not spec.reserved and spec.key not in corpus
    ]
    assert dead == [], (
        f"Flags registradas SIN consumidor en código productivo: {dead}. "
        "O se cablean, o se marcan reserved=True con reserved_reason "
        "y se agregan a RESERVED_KEYS de este test."
    )

def test_reserved_set_is_frozen():
    actual = {spec.key for spec in FLAG_REGISTRY if spec.reserved}
    assert actual == RESERVED_KEYS

def test_reserved_flags_declare_reason():
    for spec in FLAG_REGISTRY:
        if spec.reserved:
            assert spec.reserved_reason.strip(), f"{spec.key} sin reserved_reason"

def test_reserved_flags_are_actually_dead(corpus):
    """Anti-deriva inversa: si alguien cablea una reservada, DEBE quitarle la marca."""
    alive = [k for k in RESERVED_KEYS if k in corpus]
    assert alive == [], (
        f"Flags marcadas reserved pero CON consumidor real: {alive}. "
        "Quitarles reserved=True (ya están vivas)."
    )

def test_read_current_exposes_reserved_fields():
    from services.harness_flags import read_current
    flags = {f["key"]: f for f in read_current()}
    assert flags["STACKY_BUDGET_PER_TICKET_USD"]["reserved"] is True
    assert flags["STACKY_BUDGET_PER_TICKET_USD"]["reserved_reason"]
    assert flags["STACKY_RUN_ADVISOR_ENABLED"]["reserved"] is False
