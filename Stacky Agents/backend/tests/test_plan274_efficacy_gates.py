"""
test_plan274_efficacy_gates.py — Plan 274 F10 [ADICION ARQUITECTO v3].

POR QUE EXISTE. Las tres bloqueantes de la critica v2->v3 comparten UNA firma:
el criterio verificaba que el codigo estuviera ESCRITO, no que HICIERA algo.

  V1 (alcance)   — `_check_deadline` es un closure anidado en
                   `_run_pipeline_stages`. Llamarlo desde otra funcion es
                   NameError en runtime, y `compileall` da VERDE. Peor: el gate
                   del v2 era `grep -c "_check_deadline(" >= 9`, o sea que
                   METER EL BUG SUBIA EL PUNTAJE (3 -> 4, acercandose a 9).
  V2 (inercia)   — un presupuesto de capturas cuyo indice era `0` fijo no puede
                   activarse nunca; el criterio sintactico cerraba la fase con
                   cero PNG de diferencia.
  V6 (flag muda) — dos flags registradas en los 5 archivos del arnes y leidas
                   por NADIE pasaban el gate de patas, que verifica registro y
                   no efecto.

F10 agrega dos gates deterministas, sin dependencias nuevas, que corren contra
la CLASE entera y que un modelo menor no puede satisfacer escribiendo codigo
muerto.
"""
from __future__ import annotations

import ast
import pathlib
import re

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
# El tool NO vive dentro de backend/: misma resolucion que api/qa_uat.py:59-63.
_TOOL = _BACKEND.parent.parent / "Stacky tools" / "QA UAT Agent"
_PIPELINE = _TOOL / "qa_uat_pipeline.py"

_FD = (ast.FunctionDef, ast.AsyncFunctionDef)

# Las 6 flags de §3.1, todas ON.
_FLAGS_DEL_PLAN = (
    "STACKY_QA_UAT_SCREENSHOT_BUDGET_ENABLED",
    "STACKY_QA_UAT_STATE_WAITS_ENABLED",
    "STACKY_QA_UAT_RESPECT_WORKERS_ENABLED",
    "STACKY_QA_UAT_DEEPLINK_PROBE_ENABLED",
    "STACKY_QA_UAT_DATA_CACHE_ENABLED",
    "STACKY_QA_UAT_STAGE_DEADLINE_ENABLED",
)

_EXCLUIDOS = re.compile(r"__pycache__|[\\/]tests[\\/]|_attic|[\\/]evals[\\/]")


# ── F10.1 — gate de ALCANCE (mata la clase de V1) ────────────────────────────

def _closures_fuera_de_scope(source: str) -> list[str]:
    """Toda funcion ANIDADA llamada por nombre fuera del cuerpo de su padre.

    Detecta el NameError en runtime que `compileall` no ve, para CUALQUIER
    closure del archivo — no solo `_check_deadline`.
    """
    tree = ast.parse(source)

    top_level: set[str] = set()                      # visibles desde cualquier lado
    nested: dict[str, list[tuple]] = {}              # name -> [(def, padre, ini, fin)]

    def visit(node, parent_fn):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _FD):
                if parent_fn is None:
                    top_level.add(child.name)
                else:
                    nested.setdefault(child.name, []).append(
                        (child.lineno, parent_fn.name, parent_fn.lineno, parent_fn.end_lineno))
                visit(child, child)
            else:
                visit(child, parent_fn)

    visit(tree, None)

    violaciones = []
    for name, definiciones in nested.items():
        if name in top_level:
            continue          # tambien existe a nivel modulo: llamarla es legal
        llamadas = [n.lineno for n in ast.walk(tree)
                    if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Name) and n.func.id == name]
        for linea in llamadas:
            if not any(ini <= linea <= fin for (_d, _p, ini, fin) in definiciones):
                padres = ", ".join(f"{p} (:{ini}-{fin})" for (_d, p, ini, fin) in definiciones)
                violaciones.append(
                    f"{name} definida en :{definiciones[0][0]} y llamada en :{linea}, "
                    f"fuera de {padres}")
    return violaciones


def test_toda_llamada_a_closure_esta_en_su_scope():
    """Centinela: hoy `qa_uat_pipeline.py` tiene 1 closure y 0 violaciones."""
    assert _PIPELINE.is_file(), f"no se encontro el pipeline del tool en {_PIPELINE}"
    violaciones = _closures_fuera_de_scope(_PIPELINE.read_text(encoding="utf-8"))
    assert not violaciones, (
        "llamadas a funciones anidadas fuera del scope de su padre (NameError en "
        "la primera corrida real; compileall NO lo detecta):\n  - "
        + "\n  - ".join(violaciones))


def test_el_gate_de_alcance_detecta_el_defecto_del_v2():
    """CASO ADVERSO — sin esto, F10.1 no esta hecha.

    Reproduce el defecto EXACTO del v2 sobre el archivo REAL: insertar
    `_check_deadline(...)` junto a `stages["dossier"]`, que vive en
    `_run_dossier_and_publisher`, fuera del closure de `_run_pipeline_stages`.

    Con ese defecto puesto:
        python -m compileall      -> VERDE
        grep -c "_check_deadline(" -> SUBE (el gate del v2 PREMIA el bug)
        este gate                  -> ROJO
    """
    fuente = _PIPELINE.read_text(encoding="utf-8")
    lineas = fuente.splitlines()

    idx = next((i for i, l in enumerate(lineas) if 'stages["dossier"]' in l and "=" in l), None)
    assert idx is not None, (
        'no se encontro la asignacion stages["dossier"] — el caso adverso quedo '
        "sin anclaje; re-anclar por estructura antes de confiar en este gate")

    sangria = " " * (len(lineas[idx]) - len(lineas[idx].lstrip()))
    mutado = lineas[:idx] + [f"{sangria}_check_deadline(\"dossier\")"] + lineas[idx:]
    fuente_mutada = "\n".join(mutado)

    # (a) el defecto compila: por eso compileall no sirve de gate
    compile(fuente_mutada, "<mutado>", "exec")

    # (b) el grep del v2 PREMIA el bug: sube el conteo
    antes = len(re.findall(r"_check_deadline\(", fuente))
    despues = len(re.findall(r"_check_deadline\(", fuente_mutada))
    assert despues == antes + 1, (
        "el caso adverso no inyecto la llamada; sin eso no se prueba nada")

    # (c) el gate de alcance lo marca
    violaciones = _closures_fuera_de_scope(fuente_mutada)
    assert violaciones, (
        "el gate de alcance NO detecto el defecto del v2: una llamada a "
        "_check_deadline dentro de _run_dossier_and_publisher tiene que dar ROJO")
    assert any("_check_deadline" in v for v in violaciones), violaciones


# ── F10.2 — gate de FLAG VIVA (mata la clase de V6) ──────────────────────────

def _archivos_de_lectura() -> list[pathlib.Path]:
    out = []
    for patron in ("*.py", "*.j2"):
        for p in _TOOL.rglob(patron):
            if not _EXCLUIDOS.search(str(p)):
                out.append(p)
    return out


def test_toda_flag_del_plan_es_leida():
    """La pata 7 convertida en test: una flag registrada y no leida MIENTE.

    Una flag presente en los 5 archivos de registro del arnes y leida en 0
    aparece en el panel del operador con un interruptor que no hace nada — peor
    que no tenerla.
    """
    assert _TOOL.is_dir(), f"no se encontro el tool en {_TOOL}"
    archivos = _archivos_de_lectura()
    assert archivos, f"no se encontraron .py/.j2 de produccion en {_TOOL}"

    mudas = []
    for key in _FLAGS_DEL_PLAN:
        lectores = [p.relative_to(_TOOL).as_posix() for p in archivos
                    if key in p.read_text(encoding="utf-8", errors="replace")]
        if not lectores:
            mudas.append(key)

    assert not mudas, (
        "flags registradas en el arnes que NADIE lee dentro del tool "
        f"(pata 7 = 0): {mudas}. El problema no es que falte registrarlas: es "
        "que ninguna rama de codigo las consulta, asi que apagarlas no cambia "
        "nada y el 'rollback por flag' es ficticio.")


def test_toda_flag_del_plan_llega_al_tool():
    """SEXTA PATA, descubierta al implementar — el plan no la nombra.

    El pipeline corre in-process pero sus modulos leen por `os.environ`, y quien
    puebla ese entorno es `_export_qa_uat_flags()`, que itera una TUPLA EXPLICITA
    (`api/qa_uat.py:82`). Una flag ausente de esa tupla nunca se exporta: el tool
    hace `os.environ.get(KEY, "true")`, jamas ve el valor apagado y el toggle del
    panel NO HACE NADA — con las 5 patas de registro y la pata 7 en verde.

    Es la misma clase que V6 (flag muerta) por otro mecanismo, y el propio modulo
    lo advierte: "Sin esta exportacion el toggle de la UI no tendria ningun
    efecto sobre el tool".
    """
    qa_uat = _BACKEND / "api" / "qa_uat.py"
    # Se parsea con `ast`, no con split(): un parentesis dentro de un comentario
    # o de un string truncaria el bloque y el gate mediria otra cosa.
    arbol = ast.parse(qa_uat.read_text(encoding="utf-8"))
    exportadas: set[str] = set()
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "_QA_UAT_FLAG_KEYS"
                   for t in nodo.targets):
            continue
        exportadas = {e.value for e in ast.walk(nodo.value)
                      if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    assert exportadas, "no se encontro la tupla _QA_UAT_FLAG_KEYS en api/qa_uat.py"
    sin_exportar = [k for k in _FLAGS_DEL_PLAN if k not in exportadas]
    assert not sin_exportar, (
        f"flags que nunca llegan al entorno del tool: {sin_exportar}. "
        f"Agregarlas a _QA_UAT_FLAG_KEYS en {qa_uat.name}, o su interruptor en "
        "el panel del operador sera decorativo.")
