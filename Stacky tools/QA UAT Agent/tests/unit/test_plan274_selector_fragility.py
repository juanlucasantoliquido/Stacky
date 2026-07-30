"""
test_plan274_selector_fragility.py — Plan 274 F5.

Saber CUALES de los ~140 selectores (105 `locator(` + 35 `#c_`) son bombas de
tiempo, y que agregar uno nuevo peor que el peor de hoy de ROJO.

NO SE MIGRA A `getByRole`. AgendaWeb es ASP.NET WebForms: no expone roles ni
test-ids (H5: getByRole=0, getByLabel=0, getByTestId=0 en los 5 specs y en el
template). Exigirlo seria inventar alcance sobre una app que el equipo QA no
controla. Lo que si se puede es MEDIR la fragilidad y anclar por contrato.

CRITERIO DELTA, NO ABSOLUTO: el subsistema arranca con deuda (los `#c_...` son
IDs que genera ASP.NET desde la jerarquia de controles; cambiar un contenedor en
el `.aspx` los renombra en masa). Un umbral absoluto lo dejaria rojo de fabrica
por deuda preexistente.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parents[2]
REPORTS = TOOL_ROOT / "reports"
BASELINE = REPORTS / "plan274_selector_baseline.json"

SPECS: tuple[str, ...] = (
    "playwright/uat/ado120_obligaciones.spec.ts",
    "playwright/uat/ado122_provincia_domicilio.spec.ts",
    "playwright/uat/ado171_emails_oficial.spec.ts",
    "playwright/uat/frm_detalle_clie.spec.ts",
    "playwright/smoke/compromiso_minimo.spec.ts",
)
TEMPLATE = TOOL_ROOT / "templates" / "playwright_test.spec.ts.j2"

_SELECTOR_RE = re.compile(r"""(?:page\.)?locator\(\s*(['"`])(?P<sel>.+?)\1""")
_SEMANTICOS = ("getByRole", "getByLabel", "getByTestId")


def _fuentes() -> list[Path]:
    return [TOOL_ROOT / s for s in SPECS] + [TEMPLATE]


def _selectores() -> dict[str, str]:
    """selector -> primer archivo:linea donde aparece. Clave = el selector."""
    out: dict[str, str] = {}
    for p in _fuentes():
        if not p.is_file():
            continue
        for i, linea in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for m in _SELECTOR_RE.finditer(linea):
                sel = m.group("sel")
                if sel and sel not in out:
                    out[sel] = f"{p.name}:{i}"
    return out


def _scores() -> dict[str, float]:
    from locator_quality import score_alias
    return {sel: round(score_alias({"alias": sel, "selector": sel}).score, 4)
            for sel in _selectores()}


def test_baseline_existe_o_se_crea():
    """Primera corrida: genera el baseline con el score de cada selector."""
    scores = _scores()
    assert scores, "no se extrajo ningun selector de los 5 specs + el template"
    if not BASELINE.is_file():
        REPORTS.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps({"scores": scores, "fuentes": _selectores()},
                       ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert data["scores"], "el baseline de selectores quedo vacio"


def test_ningun_selector_empeora_el_baseline():
    """Assert POR SELECTOR, con las dos puntuaciones en el mensaje de fallo."""
    base = json.loads(BASELINE.read_text(encoding="utf-8"))["scores"]
    actual = _scores()
    peores = [f"{sel}: {base[sel]} -> {score}"
              for sel, score in actual.items()
              if sel in base and score < base[sel]]
    assert not peores, (
        "selectores que EMPEORARON respecto del baseline:\n  - "
        + "\n  - ".join(peores)
        + "\n(criterio DELTA: la deuda preexistente se tolera, agregar deuda nueva no)")


def test_cero_selectores_semanticos_es_el_hecho_de_hoy():
    conteo = {s: 0 for s in _SEMANTICOS}
    for p in [TOOL_ROOT / s for s in SPECS]:
        if not p.is_file():
            continue
        texto = p.read_text(encoding="utf-8")
        for s in _SEMANTICOS:
            conteo[s] += texto.count(s)
    assert conteo == {s: 0 for s in _SEMANTICOS}, (
        f"H5: WebForms no expone roles/test-ids; si este test falla es porque "
        f"alguien logro agregar uno — actualiza el numero, es una mejora. {conteo}")
