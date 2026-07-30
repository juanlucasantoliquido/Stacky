"""
test_plan274_baseline.py — Plan 274 F0.1 / F0.4.

Congela los numeros de HOY para que cualquier mejora sea demostrable y
cualquier regresion, visible. Sin baseline, "mas rapido" es una opinion.

REGLA DURA (F0.1): el baseline vive en un ARCHIVO DE DATOS, no en un assert.
Ninguna fase de este plan edita un assert para poner verde un criterio: F1 baja
el numero real y el ratchet monotono sigue verde solo.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parents[2]
REPORTS = TOOL_ROOT / "reports"
WAIT_BASELINE = REPORTS / "plan274_wait_baseline.json"

# Lista CERRADA de specs vivos (§5/F0.1). Ninguna fase la amplia.
SPECS: tuple[str, ...] = (
    "playwright/uat/ado120_obligaciones.spec.ts",
    "playwright/uat/ado122_provincia_domicilio.spec.ts",
    "playwright/uat/ado171_emails_oficial.spec.ts",
    "playwright/uat/frm_detalle_clie.spec.ts",
    "playwright/smoke/compromiso_minimo.spec.ts",
)

TEMPLATE = TOOL_ROOT / "templates" / "playwright_test.spec.ts.j2"

_WAIT_RE = re.compile(r"waitForTimeout\((\d+)\)")


def _spec_paths() -> list[Path]:
    return [TOOL_ROOT / s for s in SPECS]


def _sum_fixed_waits(paths: list[Path]) -> tuple[int, int]:
    """Devuelve (ocurrencias, total_ms) de waitForTimeout(<N>) en `paths`."""
    occurrences = 0
    total_ms = 0
    for p in paths:
        if not p.is_file():
            continue
        for m in _WAIT_RE.finditer(p.read_text(encoding="utf-8")):
            occurrences += 1
            total_ms += int(m.group(1))
    return occurrences, total_ms


def _read_baseline() -> dict:
    return json.loads(WAIT_BASELINE.read_text(encoding="utf-8"))


# ── F0.1 — baseline congelado en archivo de datos ────────────────────────────

def test_congela_el_baseline_pre_plan():
    """Escribe el baseline UNA sola vez. Si existe, no lo toca (inmutable)."""
    if not WAIT_BASELINE.is_file():
        occ, total = _sum_fixed_waits(_spec_paths())
        REPORTS.mkdir(parents=True, exist_ok=True)
        WAIT_BASELINE.write_text(
            json.dumps({"pre_plan": {"total_ms": total, "ocurrencias": occ}},
                       ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    data = _read_baseline()
    assert "pre_plan" in data, (
        f"{WAIT_BASELINE} existe pero no tiene la clave 'pre_plan'. "
        "El valor pre_plan es INMUTABLE: describe el pasado, no el presente."
    )
    assert set(data["pre_plan"]) >= {"total_ms", "ocurrencias"}


def test_no_empeora_respecto_del_baseline():
    """Ratchet monotono: F1 lo hace bajar y el test sigue verde sin editar nada."""
    base = _read_baseline()["pre_plan"]["total_ms"]
    _, actual = _sum_fixed_waits(_spec_paths())
    assert actual <= base, (
        f"REGRESION: los specs vivos suman {actual} ms de espera fija, "
        f"por encima del baseline pre-plan de {base} ms."
    )


def test_el_baseline_pre_plan_es_35900():
    """Unico lugar donde vive el numero. No cambia NUNCA: describe el pasado."""
    base = _read_baseline()["pre_plan"]
    assert base["total_ms"] == 35_900, (
        f"el baseline grabado dice {base['total_ms']} ms; el medido el 2026-07-30 "
        "era 35900. Si esto falla, el archivo de baseline fue reescrito."
    )
    assert base["ocurrencias"] == 26, (
        f"el baseline grabado dice {base['ocurrencias']} ocurrencias; eran 26."
    )


def test_generador_tiene_una_espera_fija():
    """KPI-2. F1 lo baja CAMBIANDO EL CODIGO, no el test.

    El assert es `<= 1` con el detalle de las lineas residuales en el mensaje,
    para que bajar a 0 no obligue a editar este archivo.
    """
    text = TEMPLATE.read_text(encoding="utf-8")
    lineas = [i + 1 for i, l in enumerate(text.splitlines())
              if "waitForTimeout(" in l]
    assert len(lineas) <= 1, (
        f"KPI-2: el generador maestro tiene {len(lineas)} esperas de reloj "
        f"(lineas {lineas}); el baseline pre-plan era 1 y la meta es 0. "
        "Toda espera fija en el template CONTAGIA a todo spec futuro."
    )


# ── F0.4 — centinela del reuso de sesion (lo que NO hay que romper) ──────────

def test_reuso_de_sesion_intacto():
    """El paso [7] de §2.2 es lo mejor del subsistema. Si esto falla, revertir."""
    msg = ("el reuso de sesion del §2.2[7] es lo mejor del subsistema — "
           "si este test falla, alguien lo rompio; revertir.")

    config = TOOL_ROOT / "playwright.config.ts"
    assert config.is_file(), f"{msg} (falta playwright.config.ts)"
    assert "storageState: '.auth/agenda.json'" in config.read_text(encoding="utf-8"), (
        f"{msg} (playwright.config.ts ya no persiste storageState en .auth/agenda.json)"
    )

    setup = TOOL_ROOT / "playwright" / "global.setup.ts"
    assert setup.is_file(), f"{msg} (falta playwright/global.setup.ts)"
    assert "validateAuthState" in setup.read_text(encoding="utf-8"), (
        f"{msg} (global.setup.ts ya no valida la sesion viva antes de confiar en la cookie)"
    )

    validator = TOOL_ROOT / "playwright" / "auth_state_validator.ts"
    assert validator.is_file(), f"{msg} (falta playwright/auth_state_validator.ts)"
