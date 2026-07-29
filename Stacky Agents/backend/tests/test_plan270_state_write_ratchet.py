"""Plan 270 F6 — Ratchet del censo de escrituras de estado del tracker.

CUENTA POR AST, NO POR REGEX. Contar con expresiones regulares cuenta tambien
DOCSTRINGS: medido, `grep -cE "provider\\.update_item_state\\("` sobre
harness/task_states.py da 2 y una de las dos es la prosa de su docstring. Un
ast.Call sobre un ast.Attribute no puede confundir prosa con codigo.

ALCANCE DELIBERADAMENTE ACOTADO A LO QUE ESTE PLAN POSEE: api/tickets.py.
El censo REPO-WIDE (backend/ entero) es del plan 271, que lo implementa en su
propio archivo. Dos ratchets barriendo el mismo arbol con reglas distintas se
pisan y se apagan mutuamente.

NO se arregla subiendo el numero. Se arregla enrutando el sitio nuevo por
services.tracker_write_router, o agregando un carve-out al plan y bajandolo.

No toca DB, no toca red: lee archivos con pathlib y cuenta con ast.
6 casos.
"""
import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent  # .../backend
TARGET_METHODS = frozenset({"update_item_state", "update_work_item_state"})

# Escrituras de estado que TODAVIA viven en api/tickets.py, por funcion.
# Formato: {nombre_de_funcion: (cantidad_esperada, por_que_sigue_ahi)}
# MEDIDO con el censo AST despues de implementar F3 (las lineas se corrieron,
# los conteos NO): finish_work :2135/:2137, set_stacky_status_by_ado :1505/:1507,
# create_child_task :4856/:4858.
FROZEN_TICKETS_STATE_WRITES: dict[str, tuple[int, str]] = {
    # S1/S2: quedan las DOS entradas de cada uno (provider + cliente ADO), pero
    # ya detras de la rama `else` de rollback, que solo corre con la flag OFF.
    "finish_work": (2, "S1 - rama else de rollback (flag OFF), plan 270 F3"),
    "set_stacky_status_by_ado": (2, "S2 - rama else de rollback (flag OFF), plan 270 F3"),
    # S3: carve-out, eje del plan 70. Este plan NO lo toca.
    "create_child_task": (2, "S3 - estado inicial de Task nueva, eje plan 70"),
}

PLAN270_TEST_FILES = (
    "test_plan270_close_intent.py",
    "test_plan270_write_router.py",
    "test_plan270_gitlab_close.py",
    "test_plan270_finish_work_state.py",
    "test_plan270_state_writeback.py",
    "test_plan270_state_write_ratchet.py",
)
SCRIPTS = BACKEND / "scripts"

_COMO_ARREGLARLO = (
    "no subas el numero: enruta el sitio nuevo por services.tracker_write_router"
)


def _writes_by_function(rel: str) -> dict[str, int]:
    """{nombre_funcion: cantidad de llamadas a los metodos de escritura}."""
    tree = ast.parse((BACKEND / rel).read_text(encoding="utf-8", errors="replace"))
    fns = [n for n in ast.walk(tree)
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    out: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
           and node.func.attr in TARGET_METHODS:
            owner = max(
                (f for f in fns
                 if f.lineno <= node.lineno <= (f.end_lineno or f.lineno)),
                key=lambda f: f.lineno, default=None,
            )
            name = owner.name if owner else "<module>"
            out[name] = out.get(name, 0) + 1
    return out


def _funcion(rel: str, nombre: str):
    tree = ast.parse((BACKEND / rel).read_text(encoding="utf-8", errors="replace"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == nombre:
            return node
    return None


def test_1_los_conteos_congelados_no_pueden_subir():
    real = _writes_by_function("api/tickets.py")
    for fn, (esperado, motivo) in FROZEN_TICKETS_STATE_WRITES.items():
        encontrado = real.get(fn, 0)
        assert encontrado == esperado, (
            f"api/tickets.py::{fn} escribe estado {encontrado} vez/veces y el "
            f"ratchet congela {esperado}. Motivo congelado: {motivo}. "
            f"{_COMO_ARREGLARLO}."
        )


def test_2_no_aparecio_una_funcion_nueva_que_escriba_estado():
    """Caza una funcion NUEVA aunque los conteos de las tres viejas no cambien.

    Es el caso que un ratchet de "suma total" deja pasar.
    """
    real = set(_writes_by_function("api/tickets.py"))
    congeladas = set(FROZEN_TICKETS_STATE_WRITES)
    nuevas = real - congeladas
    assert nuevas == set(), (
        f"funciones NUEVAS que escriben estado en api/tickets.py: {sorted(nuevas)}. "
        f"{_COMO_ARREGLARLO}."
    )
    assert congeladas - real == set(), (
        f"desaparecieron del archivo: {sorted(congeladas - real)}. Si fue "
        "deliberado, bajá el numero y documentá por que."
    )


def test_3_anti_gaming_el_router_no_es_un_escondite():
    """Nadie "cumple" el ratchet moviendo el problema adentro del router ni
    invirtiendo la dependencia services -> capa web."""
    router = _writes_by_function("services/tracker_write_router.py")
    assert router == {"write_state_for_ticket": 2}, (
        f"el router tiene escrituras fuera de write_state_for_ticket: {router}. "
        "Las dos esperadas son la rama ado_client y la rama provider."
    )
    # La capa de servicios no puede importar la capa web (regla del repo).
    for rel in ("services/tracker_write_router.py", "services/ticket_state_writeback.py"):
        src = (BACKEND / rel).read_text(encoding="utf-8", errors="replace")
        for ofensor in ("api.tickets", "from api ", "from api."):
            assert ofensor not in src, f"{rel} acopla services -> capa web: {ofensor!r}"


def test_4_el_archivo_existe_y_parsea():
    """Un ratchet que se apaga en silencio es peor que no tenerlo: si alguien
    renombra o rompe api/tickets.py, esto falla por archivo faltante/SyntaxError,
    NO por 0 hits."""
    p = BACKEND / "api/tickets.py"
    assert p.is_file(), f"{p} no existe: el ratchet quedaria midiendo la nada"
    ast.parse(p.read_text(encoding="utf-8", errors="replace"))
    assert _writes_by_function("api/tickets.py"), "0 hits: el ratchet dejo de medir"


def test_5_centinela_del_residuo_s5():
    """El asterisco del KPI (seccion 1) deja de ser una promesa de papel.

    S5 = services/agent_completion_internal.py::_attempt_state_change escribe
    SIEMPRE en Azure DevOps, sin mirar el tracker del proyecto. Es del plan 271 y
    este plan NO lo toca: solo lo LEE con ast.parse.
    """
    rel = "services/agent_completion_internal.py"
    real = _writes_by_function(rel)
    mensaje = (
        "S5 cambio: alguien (probablemente el plan 271) enruto "
        "_attempt_state_change por provider. El residuo declarado en el "
        "asterisco del KPI del plan 270 YA NO EXISTE: actualiza la seccion 1 y "
        "re-medi la divergencia. NO subas el numero ni borres este test."
    )
    assert real.get("_attempt_state_change", 0) == 1, mensaje

    fn = _funcion(rel, "_attempt_state_change")
    assert fn is not None, mensaje
    prohibidos = {"get_tracker_provider", "tracker_type", "_provider_for_ticket"}
    referencias = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Name):
            referencias.add(node.id)
        elif isinstance(node, ast.Attribute):
            referencias.add(node.attr)
        elif isinstance(node, ast.keyword) and node.arg:
            referencias.add(node.arg)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            referencias.add(node.value)
    assert prohibidos & referencias == set(), mensaje


def test_6_los_seis_archivos_de_test_estan_en_LOS_DOS_arneses():
    """El registro en los dos arneses deja de ser un paso manual.

    MEDIDO: el .ps1 evaluado tiene 623 entradas contra 688 del .sh, o sea 65
    tests registrados SOLO en el .sh, y nadie se enteraba porque el meta-test
    solo parsea el .sh. Entre esos 65 estaban los tests de la bandeja del plan
    238 — el plan que este 270 continua.

    Alcance acotado a los 6 archivos de ESTE plan a proposito: un gate de
    paridad repo-wide naceria rojo con 65 deudas ajenas.
    """
    sh = (SCRIPTS / "run_harness_tests.sh").read_text(encoding="utf-8", errors="replace")
    ps1 = (SCRIPTS / "run_harness_tests.ps1").read_text(encoding="utf-8", errors="replace")
    faltantes = []
    for nombre in PLAN270_TEST_FILES:
        if nombre not in sh:
            faltantes.append((nombre, "sh"))
        if nombre not in ps1:
            faltantes.append((nombre, "ps1"))
    assert faltantes == [], "; ".join(
        f"`{n}` falta en `{cual}`. El meta-test del arnes solo parsea el .sh, "
        "asi que el .ps1 se desincroniza en silencio: medido, 65 tests estan en "
        "el .sh y no en el .ps1. Agregalo a los DOS."
        for n, cual in faltantes
    )
