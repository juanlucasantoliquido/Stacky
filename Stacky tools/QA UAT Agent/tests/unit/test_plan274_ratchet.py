"""
test_plan274_ratchet.py — Plan 274 F8.2.

Que el trabajo de F1..F7 no se deshaga.

TODOS LOS CRITERIOS SON DELTA contra un artefacto de baseline, nunca umbrales
absolutos: el subsistema arranca con deuda y un umbral absoluto lo dejaria rojo
de fabrica.

`test_el_reloj_de_pared_no_empeora` NO vive aca: vive en
`test_plan274_wallclock.py` (F9). Listarlo en los dos archivos es como quedo el
v2 — y entonces ninguno lo reclamaba.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parents[2]
REPORTS = TOOL_ROOT / "reports"
WAIT_BASELINE = REPORTS / "plan274_wait_baseline.json"
TEMPLATE = TOOL_ROOT / "templates" / "playwright_test.spec.ts.j2"
RUNNER = TOOL_ROOT / "uat_test_runner.py"

SPECS: tuple[str, ...] = (
    "playwright/uat/ado120_obligaciones.spec.ts",
    "playwright/uat/ado122_provincia_domicilio.spec.ts",
    "playwright/uat/ado171_emails_oficial.spec.ts",
    "playwright/uat/frm_detalle_clie.spec.ts",
    "playwright/smoke/compromiso_minimo.spec.ts",
)

# Valores de CIERRE del plan (§8/F8.1). Congelar 6 y 7 —como hacia el v2— le
# regalaria UNA UNIDAD DE HOLGURA a cada metrica: un modulo podria desconectarse
# sin romper nada.
CIERRE_DIRECT = 5
CIERRE_ALCANZABLE = 6

# Las 4 capturas que quedan sin guardia, por ARTEFACTO (no por numero de linea:
# insertar el bloque de presupuesto corrio todo el `.j2`).
SIN_GUARDIA = ("step_00_setup.png", "step_final_state.png",
               "step_aftereach_state.png", "aspnet_exception_step_")

_WAIT_RE = re.compile(r"waitForTimeout\((\d+)\)")


def test_no_vuelven_las_esperas_fijas():
    """Criterio DELTA contra `plan274_wait_baseline.json` (el artefacto de F0.1).

    (El v1 leia este numero de `plan274_selector_baseline.json`, que es el
    artefacto de F5 y contiene SCORES DE SELECTORES, no milisegundos.)
    """
    base = json.loads(WAIT_BASELINE.read_text(encoding="utf-8"))["pre_plan"]["total_ms"]
    total = 0
    detalle = []
    for s in SPECS:
        p = TOOL_ROOT / s
        if not p.is_file():
            continue
        for i, linea in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for m in _WAIT_RE.finditer(linea):
                total += int(m.group(1))
                detalle.append(f"{s}:{i} ({m.group(1)} ms)")
    assert total <= base, (
        f"volvieron las esperas de reloj: {total} ms contra un baseline pre-plan "
        f"de {base} ms.\n  " + "\n  ".join(detalle))


def test_el_generador_no_recupera_capturas_incondicionales():
    """Conjunto EXACTO por artefacto, no un umbral."""
    lineas = TEMPLATE.read_text(encoding="utf-8").splitlines()
    sobrantes = []
    encontradas = set()
    for i, linea in enumerate(lineas):
        if "page.screenshot(" not in linea:
            continue
        # El cuerpo de __captureIfBudget es la guardia misma, no un call site.
        if "async function __captureIfBudget" in "\n".join(lineas[max(0, i - 3):i]):
            continue
        ctx = "\n".join(lineas[max(0, i - 4): i + 5])
        art = next((a for a in SIN_GUARDIA if a in ctx), None)
        if art and art not in encontradas:
            encontradas.add(art)
        else:
            sobrantes.append(f":{i + 1}")
    assert not sobrantes, (
        f"capturas incondicionales nuevas en el generador, lineas {sobrantes}. "
        f"Las unicas permitidas son las 4 de evidencia minima {list(SIN_GUARDIA)}.")
    assert encontradas == set(SIN_GUARDIA), (
        f"desaparecieron capturas de evidencia minima: {set(SIN_GUARDIA) - encontradas}")


def test_el_censo_no_crece():
    """CORRE CONTRA EL DEFECTO: desconectar cualquiera de los 5 modulos que
    conectan F2/F4/F5/F6/F7 sube `direct` a 6 y esto da ROJO. Con los valores
    del v2 (6 y 7) esa misma desconexion daba VERDE.

    El corpus NO se amplia: un modulo nuevo huerfano no rompe este test (seria
    alcance infinito). Se declara asi explicitamente.
    """
    from tests.unit.test_plan274_orphan_census import (
        ORPHAN_CORPUS, direct_importers, prod_reachable)

    huerfanos = [m for m in ORPHAN_CORPUS if not direct_importers(m)]
    inalcanzables = [m for m in ORPHAN_CORPUS if not prod_reachable(m)]
    assert len(huerfanos) <= CIERRE_DIRECT, (
        f"el censo CRECIO: {len(huerfanos)} modulos sin importador directo "
        f"(cierre del plan: {CIERRE_DIRECT}). Huerfanos: {huerfanos}")
    assert len(inalcanzables) <= CIERRE_ALCANZABLE, (
        f"el censo CRECIO: {len(inalcanzables)} modulos sin alcance de produccion "
        f"(cierre del plan: {CIERRE_ALCANZABLE}). Inalcanzables: {inalcanzables}")


def test_workers_no_se_rehardcodea():
    src = RUNNER.read_text(encoding="utf-8")
    assert '"--workers=1"' not in src, (
        "volvio el literal de workers fijo en el comando CLI: la config del "
        "operador vuelve a ser una mentira")
