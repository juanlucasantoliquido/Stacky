"""
test_plan274_screenshot_budget_wired.py — Plan 274 F2.

Conecta `screenshot_budget.py` (huerfano #9) al generador maestro.

QUE GANA F2, SIN MAQUILLAJE (corregido en v3 — hallazgo V2):
  (a) el TECHO de 25 capturas por escenario, que hoy NO EXISTE;
  (b) el `.catch(() => null)` uniforme, que hoy solo tienen 2 de las 19;
  (c) el `captureIndex` correcto, que deja el presupuesto POR PASO listo para
      activarse el dia que una rama emita una segunda captura en el mismo paso.

Lo que F2 NO gana: bajar capturas en la corrida nominal. El template ya emite
EXACTAMENTE UNA captura por paso, asi que el limite `on_success_per_step=1` no
recorta nada hoy. Prometer una reduccion que no va a ocurrir es lo que hizo que
el v2 cerrara esta fase en verde con cero PNG de diferencia.

ANCLAJE POR ESTRUCTURA, NO POR LINEA: insertar el bloque de presupuesto corre
todas las lineas del `.j2`, asi que las 4 capturas sin guardia se localizan por
su `path` y el test REPORTA los numeros nuevos en vez de fallar por el
desplazamiento.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

TOOL_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = TOOL_ROOT / "templates" / "playwright_test.spec.ts.j2"
GENERATOR = TOOL_ROOT / "playwright_test_generator.py"

# Las 4 capturas que NO llevan guardia de exito, identificadas por su artefacto:
#   step_00_setup.png        -> evidencia de setup (grupo C)
#   step_final_state.png     -> evidencia final (grupo C)
#   step_aftereach_state.png -> afterEach de fallo (grupo C)
#   aspnet_exception_step_   -> captura de ERROR, ya condicional (grupo D).
#                               Envolverla en una guardia de EXITO borraria
#                               justo la evidencia de un fallo.
SIN_GUARDIA_ESPERADAS = (
    "step_00_setup.png",
    "step_final_state.png",
    "step_aftereach_state.png",
    "aspnet_exception_step_",
)
ENVOLVIBLES = 15


def _template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def _lineas(pred) -> list[int]:
    return [i + 1 for i, l in enumerate(_template().splitlines()) if pred(l)]


def _contexto(lineno: int, radio: int = 4) -> str:
    lineas = _template().splitlines()
    return "\n".join(lineas[max(0, lineno - 1 - radio): lineno + radio])


def test_generador_importa_el_presupuesto():
    """Invierte la fila 9 del censo: screenshot_budget deja de ser huerfano."""
    src = GENERATOR.read_text(encoding="utf-8")
    assert "build_ts_budget_block" in src and "load_budget" in src, (
        "playwright_test_generator.py no importa screenshot_budget: el modulo "
        "sigue huerfano y F2 no conecto nada")


def test_template_tiene_el_bloque():
    apariciones = _lineas(lambda l: "screenshot_budget_block" in l and "{{" in l)
    assert len(apariciones) == 1, (
        f"el `.j2` tiene {len(apariciones)} apariciones de "
        f"{{{{ screenshot_budget_block }}}} (lineas {apariciones}); tiene que ser "
        "exactamente 1, en el preambulo")


def test_capturas_por_paso_estan_guardadas():
    """Conjunto EXACTO de capturas sin guardia, comparado por artefacto.

    No es un umbral: un umbral se satisface envolviendo la captura de excepcion
    (que borraria la evidencia de un fallo) o borrando el assert.
    """
    lineas = _template().splitlines()
    crudas = _lineas(lambda l: "page.screenshot(" in l)
    identificadas: dict[str, int] = {}
    sobrantes: list[str] = []
    for ln in crudas:
        # El CUERPO de __captureIfBudget no es un call site: es la guardia misma.
        # (La rama degradada del preambulo define su propio fallback.)
        anteriores = "\n".join(lineas[max(0, ln - 4): ln - 1])
        if "async function __captureIfBudget" in anteriores:
            continue
        ctx = _contexto(ln)
        match = next((a for a in SIN_GUARDIA_ESPERADAS if a in ctx), None)
        if match and match not in identificadas:
            identificadas[match] = ln
        else:
            sobrantes.append(f":{ln} -> {_template().splitlines()[ln - 1].strip()[:90]}")

    faltantes = [a for a in SIN_GUARDIA_ESPERADAS if a not in identificadas]
    assert not faltantes, (
        f"faltan capturas de evidencia minima que NO deben llevar guardia: {faltantes}. "
        "Si desaparecieron, alguien envolvio evidencia que tiene que salir siempre.")
    assert not sobrantes, (
        f"capturas SIN guardia de presupuesto que deberian estar envueltas "
        f"({len(sobrantes)}):\n  " + "\n  ".join(sobrantes) +
        f"\nLas unicas 4 permitidas son {list(SIN_GUARDIA_ESPERADAS)}; "
        f"hoy estan en {identificadas}.")


def test_no_queda_ninguna_llamada_de_aridad_uno():
    """CORRE CONTRA EL DEFECTO del v1: `__shouldCapture('success')`.

    Con 1 argumento `captureIndex` es `undefined`, `undefined >= limit` es
    `false`, no se corta nada y el presupuesto queda inerte — ademas de romper
    `tsc --noEmit` por aridad.
    """
    malas = [ln for ln in _lineas(lambda l: "__shouldCapture(" in l)
             if re.search(r"__shouldCapture\([^,)]*\)", _template().splitlines()[ln - 1])]
    assert not malas, (
        f"llamadas a __shouldCapture con un solo argumento en las lineas {malas}; "
        "la firma real es __shouldCapture(stepOk: boolean, captureIndex: number) "
        "(screenshot_budget.py:181)")


def test_captureindex_no_es_constante():
    """CORRE CONTRA EL DIFF EXACTO del v2: `__captureIfBudget(page, path, true, 0)`.

    Con `0` fijo la condicion `captureIndex >= limit` es `0 >= 1` = false PARA
    SIEMPRE: el presupuesto por paso no puede activarse nunca y la fase cierra
    en verde sin bajar un solo PNG.
    """
    t = _template()
    assert ", true, 0)" not in t, (
        "el `.j2` pasa `captureIndex = 0` literal: el presupuesto por paso queda "
        "estructuralmente inerte (0 >= 1 es false para siempre)")
    assert "__ssStepIdx" in t, (
        "no aparece el contador por paso `__ssStepIdx`: el indice tiene que "
        "representar CUAL captura de ESTE paso es")
    reinicios = _lineas(lambda l: "__ssStepIdx = 0" in l)
    assert len(reinicios) >= 2, (
        f"el contador se declara/reinicia en {reinicios}: hace falta la "
        "declaracion en el preambulo Y el reinicio al empezar cada paso")


def test_generador_degrada_si_el_presupuesto_falla(monkeypatch):
    """Config ausente o modulo roto NO puede romper la generacion de specs."""
    import playwright_test_generator as gen

    def _boom(*a, **kw):
        raise RuntimeError("config de presupuesto ausente")

    monkeypatch.setattr("screenshot_budget.load_budget", _boom)
    bloque = gen._screenshot_budget_block()
    assert bloque == "", (
        "si load_budget lanza, el generador tiene que degradar a bloque vacio, "
        f"no propagar la excepcion (devolvio {bloque[:60]!r})")

    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    env = Environment(loader=FileSystemLoader(str(TEMPLATE.parent)),
                      undefined=StrictUndefined, autoescape=False)
    rendered = env.get_template(TEMPLATE.name).render(
        ticket_id=274, scenario_id="P01", titulo="t", pantalla="FrmAgenda.aspx",
        entry_screen="FrmAgenda.aspx", precondiciones=[],
        pasos=[{"accion": "click", "target": "b", "descripcion": "d"}],
        oraculos=[], datos_requeridos=[], ui_map={"b": "#c_b"},
        detect_screen_errors=False, detect_screen_errors_vision=False,
        screen_error_detector_js="", aspnet_exception_detector_js="",
        resolved_values={}, state_waits_enabled=True, screenshot_budget_block="",
    )
    assert "__captureIfBudget" in rendered, (
        "con el bloque vacio el spec sigue llamando a __captureIfBudget pero "
        "nadie lo define: ReferenceError en runtime. El template tiene que "
        "emitir un fallback que capture sin guardia (comportamiento de hoy).")
    assert "async function __captureIfBudget" in rendered, (
        "falta la definicion de fallback de __captureIfBudget en el render degradado")
    assert "test.describe" in rendered, "el spec degradado no es un spec valido"


def test_el_techo_de_25_se_activa():
    """UNICO TEST DE EFECTO de esta fase: cuenta decisiones de captura reales.

    CORRE CONTRA EL DEFECTO: sin techo, 30 pasos producen 30 capturas y esto es
    ROJO. Con el modulo conectado, la 26a y siguientes se suprimen.
    """
    from screenshot_budget import ScreenshotBudget, should_capture

    budget = ScreenshotBudget()
    assert budget.max_total_per_scenario == 25

    decisiones = [should_capture(budget, step_ok=True, taken_so_far=n,
                                 step_capture_index=0)[0] for n in range(30)]
    assert sum(decisiones) == 25, (
        f"con 30 pasos se emitieron {sum(decisiones)} capturas; el techo de 25 "
        "por escenario no se activo")
    assert decisiones.count(False) == 5
    assert decisiones[24] is True and decisiones[25] is False, (
        "el corte no cae exactamente en la captura 26")

    razon = should_capture(budget, step_ok=True, taken_so_far=25, step_capture_index=0)[1]
    assert razon == "max_total_per_scenario_exceeded", razon


def test_la_flag_gobierna_el_bloque(monkeypatch):
    """CORRE CONTRA EL DEFECTO del v2 (hallazgo V6): la flag nueva NO esta
    cableada al modulo por si sola.

    `build_ts_budget_block` toma la rama inerte con `budget.disabled`, que solo
    lee QA_UAT_SCREENSHOT_BUDGET_DISABLED (screenshot_budget.py:99). Sin
    construir el ScreenshotBudget deshabilitado a mano, apagar la flag no hace
    absolutamente nada.
    """
    import playwright_test_generator as gen

    monkeypatch.setenv("STACKY_QA_UAT_SCREENSHOT_BUDGET_ENABLED", "true")
    monkeypatch.delenv("QA_UAT_SCREENSHOT_BUDGET_DISABLED", raising=False)
    on = gen._screenshot_budget_block()
    assert "const __SS_MAX_PER_SCENARIO = 25;" in on, on[:200]
    assert "__SS_BUDGET_DISABLED = false" in on

    monkeypatch.setenv("STACKY_QA_UAT_SCREENSHOT_BUDGET_ENABLED", "false")
    off = gen._screenshot_budget_block()
    assert "__SS_BUDGET_DISABLED = true" in off, (
        "con la flag OFF hay que emitir la rama `disabled` del modulo "
        "(rollback exacto al comportamiento historico)")
    assert "const __SS_MAX_PER_SCENARIO = Infinity;" in off
    assert on != off, (
        "los dos bloques son IDENTICOS: la flag no gobierna nada y es una flag "
        "muerta en el panel del operador")
