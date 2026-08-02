"""Plan 286 F0 — Centinela DIRIGIDO: los cuatro escritores no leen la columna.

Por que un centinela propio y no `scan_tracker_type_routing` (Plan 281 F8):
ese detector (a) es ciego al idioma `getattr(x, "tracker_type", ...)`, que es
justo el que usan los cuatro sitios, y (b) es intra-funcion, asi que no ve el
idioma "una funcion lee y otra compara". Medido el 2026-08-01: devuelve [] con
los cuatro sitios vivos. Ampliarlo abre 8 hallazgos ajenos y rompe el contrato
del Plan 281, asi que este centinela mira EXACTAMENTE los cuatro sitios.
"""
import ast
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_HELPER = "tracker_efectivo_de_ticket"

# (ruta relativa a backend/, nombre de la funcion que NO puede leer la columna).
# Lista CONGELADA: agregar un sitio nuevo es una decision del plan, no un efecto
# colateral.
SITIOS_VIGILADOS = (
    ("services/tracker_write_router.py",   "_norm_tracker_type"),
    ("services/comment_publish_router.py", "_norm_tracker_type"),
    ("services/completion_sync.py",        "_resolve_sync_and_project"),
    ("api/tickets.py",                     "_tracker_type_for"),
)

# PATA 2 (C1). (ruta, funcion|None). None => basta con que el ARCHIVO llame al
# helper, porque el eje BORRA la funcion vigilada de ese archivo (F2/F3). Con un
# nombre de funcion => la llamada tiene que estar DENTRO de esa funcion, porque
# esa funcion SOBREVIVE al eje (F4).
# Sin esta constante, borrar o renombrar la funcion vigilada deja el censo de
# ausencia verde para siempre: verde por ausencia de la funcion, no por ausencia
# del defecto. Es el falso verde que este centinela existe para no repetir.
ANCLAS_HELPER = (
    ("services/tracker_write_router.py",   None),
    ("services/comment_publish_router.py", None),
    ("services/completion_sync.py",        "_resolve_sync_and_project"),
    ("api/tickets.py",                     "_tracker_type_for"),
)


def _funcs(arbol, nombre):
    return [n for n in ast.walk(arbol)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == nombre]


def _lee_la_columna(nodo) -> bool:
    """Los DOS idiomas: `x.tracker_type` y `getattr(x, "tracker_type", ...)`."""
    if isinstance(nodo, ast.Attribute) and nodo.attr == "tracker_type":
        return True
    if isinstance(nodo, ast.Call):
        fn = nodo.func
        if isinstance(fn, ast.Name) and fn.id == "getattr" and len(nodo.args) >= 2:
            a = nodo.args[1]
            return isinstance(a, ast.Constant) and a.value == "tracker_type"
    return False


def _llama_al_helper(nodo) -> bool:
    """`tracker_efectivo_de_ticket(...)` o `<mod>.tracker_efectivo_de_ticket(...)`."""
    if not isinstance(nodo, ast.Call):
        return False
    fn = nodo.func
    if isinstance(fn, ast.Name):
        return fn.id == _HELPER
    if isinstance(fn, ast.Attribute):
        return fn.attr == _HELPER
    return False


def lectores_de_la_columna(sitios, backend=None):
    """['<ruta>::<funcion>'] por cada sitio vigilado que lee la columna."""
    raiz = backend or _BACKEND
    hallados = []
    for rel, nombre in sitios:
        arbol = ast.parse((raiz / rel).read_text(encoding="utf-8"))
        for n in _funcs(arbol, nombre):
            if any(_lee_la_columna(h) for h in ast.walk(n)):
                hallados.append(f"{rel}::{nombre}")
    return sorted(set(hallados))


def archivos_sin_anclaje(anclas, backend=None):
    """['<ruta>' | '<ruta>::<funcion>'] por cada ancla que NO llama al helper."""
    raiz = backend or _BACKEND
    faltan = []
    for rel, nombre in anclas:
        arbol = ast.parse((raiz / rel).read_text(encoding="utf-8"))
        if nombre is None:
            if not any(_llama_al_helper(n) for n in ast.walk(arbol)):
                faltan.append(rel)
            continue
        objetivo = _funcs(arbol, nombre)
        if not objetivo:
            faltan.append(f"{rel}::{nombre} (LA FUNCION NO EXISTE)")
            continue
        if not any(_llama_al_helper(h) for f in objetivo for h in ast.walk(f)):
            faltan.append(f"{rel}::{nombre}")
    return sorted(set(faltan))


def test_ningun_sitio_vigilado_lee_la_columna():
    """PATA 1 — ausencia."""
    vivos = lectores_de_la_columna(SITIOS_VIGILADOS)
    assert vivos == [], (
        f"estos escritores siguen ruteando por la columna que MIENTE: {vivos}. "
        f"Tienen que llamar a services.project_context.{_HELPER}."
    )


def test_los_cuatro_archivos_anclan_en_el_helper():
    """PATA 2 — PRESENCIA. Un assert de ausencia solo pasa por accidente: este
    guarda la presencia del anclaje EN EL MISMO eje, asi que borrar o renombrar
    la funcion vigilada NO puede apagar el centinela."""
    faltan = archivos_sin_anclaje(ANCLAS_HELPER)
    assert faltan == [], (
        f"estos sitios ya no leen la columna PERO tampoco resuelven con el "
        f"helper: {faltan}. Un centinela verde por ausencia de la funcion es un "
        f"falso verde (Plan 286 C1)."
    )


def test_el_detector_ve_los_dos_idiomas(tmp_path):
    """Calibracion 1 — el gate se corre CONTRA el defecto: si el detector no ve
    el idioma `getattr`, la pata 1 es un falso verde (le paso al Plan 281)."""
    (tmp_path / "sonda.py").write_text(
        "def por_atributo(t):\n"
        "    return t.tracker_type\n"
        "def por_getattr(t):\n"
        '    return getattr(t, "tracker_type", None)\n'
        "def limpia(t):\n"
        "    return t.stacky_project_name\n",
        encoding="utf-8",
    )
    marcadas = lectores_de_la_columna(
        (("sonda.py", "por_atributo"), ("sonda.py", "por_getattr"),
         ("sonda.py", "limpia")),
        backend=tmp_path,
    )
    assert marcadas == ["sonda.py::por_atributo", "sonda.py::por_getattr"]


def test_el_centinela_no_se_calla_si_la_funcion_desaparece(tmp_path):
    """Calibracion 2 (C1) — el modo de falla que mato a la v1: si la funcion
    vigilada se BORRA o se RENOMBRA, la pata 1 devuelve [] (nada que mirar) y la
    pata 2 tiene que GRITAR. Se prueban los dos lados en el mismo test."""
    (tmp_path / "limpio.py").write_text(
        "from services.project_context import tracker_efectivo_de_ticket\n"
        "def resolver(t):\n"
        "    return tracker_efectivo_de_ticket(t)\n",
        encoding="utf-8",
    )
    (tmp_path / "renombrado.py").write_text(
        "def otro_nombre(t):\n"
        '    return getattr(t, "tracker_type", None)\n',
        encoding="utf-8",
    )
    # (a) La pata 1 se calla cuando la funcion no existe: por eso no alcanza sola.
    assert lectores_de_la_columna(
        (("renombrado.py", "_norm_tracker_type"),), backend=tmp_path) == []
    # (b) La pata 2 lo agarra igual, por archivo...
    assert archivos_sin_anclaje(
        (("renombrado.py", None),), backend=tmp_path) == ["renombrado.py"]
    # (c) ...y por funcion inexistente, con el motivo escrito.
    assert archivos_sin_anclaje(
        (("renombrado.py", "_norm_tracker_type"),), backend=tmp_path
    ) == ["renombrado.py::_norm_tracker_type (LA FUNCION NO EXISTE)"]
    # (d) Y NO grita sobre un archivo que si ancla: la pata 2 no es un assert
    #     que siempre falla.
    assert archivos_sin_anclaje((("limpio.py", None),), backend=tmp_path) == []
    assert archivos_sin_anclaje(
        (("limpio.py", "resolver"),), backend=tmp_path) == []


def test_el_gate_282_mide_de_verdad_y_respeta_el_corte():
    """El defecto no era el TEXTO, era que la query no CORRIA. Asi que se corre.
    Contra SQLite en memoria: no importa `db`, no toca la base del operador."""
    import importlib.util, sqlite3
    from pathlib import Path

    ruta = Path(__file__).resolve().parents[1] / "scripts" / "gate_plan282.py"
    spec = importlib.util.spec_from_file_location("gate_plan282_bajo_test", ruta)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)

    # PRESENCIA (lo que TIENE que estar), guardada junto a la ausencia: un assert
    # de ausencia solo pasaria igual si la query se borrara entera.
    assert "error_message LIKE" in gate.K1_SQL
    assert "published_at > :corte" in gate.K1_SQL
    assert "reason LIKE" not in gate.K1_SQL

    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE agent_html_publish "
              "(id INTEGER, status TEXT, error_message TEXT, published_at TEXT)")
    firma = ("ADO client build failed: AdoConfigError: El proyecto 'RIPLEY' "
             "no usa Azure DevOps (tracker_type=gitlab).")
    c.executemany("INSERT INTO agent_html_publish VALUES (?,?,?,?)", [
        (56, "failed", firma, "2026-08-01 16:16:42.530521"),   # historica
        (57, "failed", firma, "2026-08-01 20:24:43.801697"),   # historica
        (58, "failed", "otro error cualquiera", "2026-09-01 00:00:00"),
        (59, "ok",     firma,                    "2026-09-01 00:00:00"),
    ])
    sql = gate.K1_SQL.replace(":corte", "?")
    assert c.execute(sql, (gate.K1_CORTE_HISTORICO,)).fetchone()[0] == 0

    # Y ahora la mitad que de verdad importa: una REGRESION tiene que contar.
    c.execute("INSERT INTO agent_html_publish VALUES (60,'failed',?, '2026-09-02 00:00:00')",
              (firma,))
    assert c.execute(sql, (gate.K1_CORTE_HISTORICO,)).fetchone()[0] == 1
