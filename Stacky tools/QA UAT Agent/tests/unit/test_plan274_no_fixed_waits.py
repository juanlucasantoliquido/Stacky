"""
test_plan274_no_fixed_waits.py — Plan 274 F1.

Que ninguna espera de RELOJ sobreviva sin un test que pruebe que la espera por
ESTADO no alcanza.

El generador va primero (es la raiz del contagio: todo spec futuro hereda el
sleep del template) y los specs vivos despues.

NINGUN test de este archivo assertea "la lista esta vacia": todos asserten POR
OCURRENCIA y con el numero de linea en el mensaje de fallo, porque un criterio
agregado se satisface borrando el assert.
"""
from __future__ import annotations

import re
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = TOOL_ROOT / "templates" / "playwright_test.spec.ts.j2"

SPECS: tuple[str, ...] = (
    "playwright/uat/ado120_obligaciones.spec.ts",
    "playwright/uat/ado122_provincia_domicilio.spec.ts",
    "playwright/uat/ado171_emails_oficial.spec.ts",
    "playwright/uat/frm_detalle_clie.spec.ts",
    "playwright/smoke/compromiso_minimo.spec.ts",
)

UMBRAL_MS = 3_000
MARCADOR_TEMPLATE = "plan-274 F1.1"
MARCADOR_SPEC = "plan-274 F1.2"
FLAG = "STACKY_QA_UAT_STATE_WAITS_ENABLED"

_WAIT_RE = re.compile(r"waitForTimeout\((\d+)\)")


def _sum_fixed_waits(paths: list[Path]) -> tuple[int, int]:
    occ = total = 0
    for p in paths:
        if not p.is_file():
            continue
        for m in _WAIT_RE.finditer(p.read_text(encoding="utf-8")):
            occ += 1
            total += int(m.group(1))
    return occ, total


def _lineas_con_espera(text: str) -> list[int]:
    return [i + 1 for i, l in enumerate(text.splitlines()) if "waitForTimeout(" in l]


def test_generador_sin_espera_fija_o_documentada():
    """Cada `waitForTimeout(` residual en el .j2 tiene que estar en la rama
    `{% else %}` del rollback por flag, o llevar el marcador `plan-274 F1.1`
    adyacente. Sin marcador -> falla NOMBRANDO la linea."""
    lineas = TEMPLATE.read_text(encoding="utf-8").splitlines()
    sin_justificar = []
    for i, linea in enumerate(lineas):
        if "waitForTimeout(" not in linea:
            continue
        # (a) rama de rollback de la flag: es el comportamiento historico exacto
        if "{% else %}" in linea and FLAG.lower().replace("stacky_qa_uat_", "") in linea.lower():
            continue
        if "{% else %}" in linea and "waitForAgendaStable" in linea:
            continue
        # (b) marcador explicito en la propia linea o en las adyacentes
        contexto = "\n".join(lineas[max(0, i - 1):i + 2])
        if MARCADOR_TEMPLATE in contexto:
            continue
        sin_justificar.append(i + 1)
    assert not sin_justificar, (
        f"esperas de reloj sin justificar en {TEMPLATE.name}, lineas {sin_justificar}. "
        "Toda espera fija del generador CONTAGIA a todo spec futuro: o se "
        f"reemplaza por espera por estado, o lleva el marcador '{MARCADOR_TEMPLATE}' "
        "explicando por que no se pudo.")


def test_specs_vivos_bajo_umbral():
    occ, total = _sum_fixed_waits([TOOL_ROOT / s for s in SPECS])
    assert total <= UMBRAL_MS, (
        f"KPI-1: los specs vivos suman {total} ms en {occ} esperas de reloj; "
        f"el umbral del plan es {UMBRAL_MS} ms (baseline pre-plan: 35900 ms / 26).")


def test_toda_espera_residual_esta_marcada():
    """Cada sleep que sobrevivio en un spec lleva el marcador con su motivo."""
    sin_marcar = []
    for s in SPECS:
        p = TOOL_ROOT / s
        if not p.is_file():
            continue
        lineas = p.read_text(encoding="utf-8").splitlines()
        for i, linea in enumerate(lineas):
            if "waitForTimeout(" not in linea:
                continue
            contexto = "\n".join(lineas[max(0, i - 1):i + 2])
            if MARCADOR_SPEC not in contexto:
                sin_marcar.append(f"{s}:{i + 1}")
    assert not sin_marcar, (
        f"esperas de reloj residuales sin el marcador '{MARCADOR_SPEC}': {sin_marcar}. "
        "Un sleep que sobrevive tiene que decir POR QUE no se pudo determinar "
        "que se estaba esperando.")


def test_la_flag_gobierna_el_render(monkeypatch):
    """CORRE CONTRA EL DEFECTO del v2: con su edicion LITERAL del .j2 los dos
    renders son identicos y este test da ROJO.

    Una flag registrada en los 5 archivos del arnes, visible en el panel del
    operador y sin ninguna rama que la consulte es una FLAG MUERTA que miente.
    """
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(str(TEMPLATE.parent)),
                      autoescape=False, keep_trailing_newline=True)
    tpl = env.get_template(TEMPLATE.name)
    ctx = dict(
        ticket_id=274, scenario_id="P01", titulo="t", pantalla="FrmAgenda.aspx",
        entry_screen="FrmAgenda.aspx", precondiciones=[],
        pasos=[{"accion": "expand_collapsible", "target": "panel", "descripcion": "d"}],
        oraculos=[], datos_requeridos=[], ui_map={"panel": "#c_panel"},
        detect_screen_errors=False, detect_screen_errors_vision=False,
        screen_error_detector_js="", aspnet_exception_detector_js="",
        resolved_values={},
    )

    con_flag = tpl.render(state_waits_enabled=True, **ctx)
    sin_flag = tpl.render(state_waits_enabled=False, **ctx)

    assert "waitForAgendaStable(page, 5_000)" in con_flag, (
        "con la flag ON el render tiene que usar la espera por ESTADO")
    assert "waitForTimeout(800)" not in con_flag, (
        "con la flag ON no puede quedar el sleep de 800 ms")

    assert "waitForTimeout(800)" in sin_flag, (
        "con la flag OFF el render tiene que emitir el sleep historico "
        "(rollback exacto sin revertir codigo)")
    assert "waitForAgendaStable(page, 5_000)" not in sin_flag, (
        "con la flag OFF no puede aparecer la espera por estado nueva")

    assert con_flag != sin_flag, (
        "los dos renders son IDENTICOS: la flag no gobierna nada. Es exactamente "
        "el defecto del v2 (hallazgo V6): edicion literal del .j2 sin rama Jinja.")
