"""tests/test_plan277_un_solo_motor.py — Plan 277 F2-bis. El KPI se vuelve un gate.

Este plan nace porque UNA convención vivió en CUATRO copias divergentes durante 8
planes sin que nada lo detectara. Consolidarlas y no dejar un gate garantiza que en
3 planes haya un motor nº 5.

POR QUÉ POR `ast` Y NO POR `grep` (v2/C13): un `grep` de substring cuenta
comentarios y docstrings, y este plan AGREGA comentarios que contienen la etiqueta
para explicar el arreglo — así que el número subiría justo después de arreglarlo.
El AST ve solo `ast.Constant`, y este archivo además descarta los docstrings.

EL CASO 4 ES EL QUE HACE QUE ESTE ARCHIVO VALGA. Un detector que nunca vio un
positivo pasa por accidente: prueba que el gate DETECTA el motor nº 5, no solo que
hoy no hay ninguno. Y siembra también el negativo (un módulo cuyo único texto
sospechoso está en un docstring), porque un detector que descarta de más daría
cero hallazgos por el motivo equivocado.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.gitlab_hierarchy import PREFIJO_PADRE, PREFIJO_TIPO  # noqa: E402

_SERVICES = _BACKEND / "services"
_CONTRATO = "gitlab_hierarchy"

# Los CUATRO motores que este plan consolida.
_MOTORES = ("gitlab_provider", "migrator_verify", "migrator_epics", "incident_context")

# El token suelto del bug histórico: `incident_context` comparaba contra la palabra
# "epic" a secas, ni siquiera contra el prefijo, así que `epic::42` —que marca a un
# HIJO— le daba True. Se busca en minúscula y exacto porque ESA es la forma del
# defecto (la comparación era contra `str(lbl).lower()`). "Epic" con mayúscula es
# el VALOR CANÓNICO que devuelve el contrato: compararse contra la salida del
# contrato es consumirlo bien, no tener un motor propio.
_TOKEN_SUELTO = "epic"

# ── La allowlist. UNA entrada. ───────────────────────────────────────────────
# `services/migrator_epics.py` es el ESCRITOR legítimo: sus `item_type_for_create`
# del camino Premium nativo (`:37`, `:50`) son el VALOR que se le manda a la API de
# GitLab al crear una épica, no una regla de clasificación — no pueden divergir de
# nadie porque no leen nada. La etiqueta del camino free_degrade ya NO está acá: la
# compone el contrato (`etiqueta_de_tipo`).
#
# El criterio es de SUBCONJUNTO, no de igualdad: si mañana esos literales se van,
# el gate no se pone rojo por una mejora; pero cualquier literal DISTINTO en ese
# mismo archivo sí lo pone.
_ESCRITOR_LEGITIMO: dict[str, set[str]] = {
    "migrator_epics.py": {"epic"},
}


def _arbol(ruta: Path) -> ast.Module:
    return ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))


def _ids_de_docstrings(arbol: ast.AST) -> set[int]:
    """`id()` de cada Constant que es docstring de módulo, clase o función."""
    ids: set[int] = set()
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        cuerpo = getattr(nodo, "body", None) or []
        if not cuerpo:
            continue
        primero = cuerpo[0]
        if isinstance(primero, ast.Expr) and isinstance(primero.value, ast.Constant) \
                and isinstance(primero.value.value, str):
            ids.add(id(primero.value))
    return ids


def _es_literal_de_clasificacion(valor: str) -> bool:
    bajo = valor.lower()
    if PREFIJO_TIPO in bajo or PREFIJO_PADRE in bajo:
        return True
    return valor.strip() == _TOKEN_SUELTO


def _literales_de_clasificacion(arbol: ast.AST) -> list[tuple[int, str]]:
    """(línea, valor) de cada literal de clasificación que NO sea docstring.

    Cubre las f-strings: `f"type::{x}"` es un `JoinedStr` cuyo prefijo es un
    `ast.Constant`, y `ast.walk` lo visita igual.
    """
    docstrings = _ids_de_docstrings(arbol)
    hallazgos: list[tuple[int, str]] = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Constant) or not isinstance(nodo.value, str):
            continue
        if id(nodo) in docstrings:
            continue
        if _es_literal_de_clasificacion(nodo.value):
            hallazgos.append((getattr(nodo, "lineno", -1), nodo.value))
    return hallazgos


def _modulos_importados(arbol: ast.AST) -> set[str]:
    """Todo lo importado, INCLUIDOS los imports locales dentro de funciones.

    `ast.walk` es lo que hace que esto funcione: el read path importa el contrato
    adentro de `_normalize_issue` para no crear un ciclo, y un chequeo que mirara
    solo `arbol.body` no lo vería y declararía el módulo "sin consolidar".
    """
    modulos: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                modulos.add(alias.name)
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.module:
                modulos.add(nodo.module)
    return modulos


# ── Caso 1 ───────────────────────────────────────────────────────────────────

def test_01_los_cuatro_motores_importan_el_contrato():
    """Que la consolidación de F2 ocurrió de verdad, y no solo en el changelog."""
    sin_contrato = []
    for nombre in _MOTORES:
        ruta = _SERVICES / f"{nombre}.py"
        assert ruta.exists(), f"no existe {ruta}"
        importados = _modulos_importados(_arbol(ruta))
        if not any(m == f"services.{_CONTRATO}" or m.endswith(f".{_CONTRATO}") or m == _CONTRATO
                   for m in importados):
            sin_contrato.append(nombre)
    assert sin_contrato == [], (
        f"estos módulos siguen sin consumir services.{_CONTRATO}: {sin_contrato}"
    )


# ── Caso 2 ───────────────────────────────────────────────────────────────────

def test_02_ningun_motor_conserva_literales_de_clasificacion_propios():
    """Que no quede lógica de clasificación propia en ninguno de los 4."""
    fuera_de_contrato: dict[str, list[tuple[int, str]]] = {}
    for nombre in _MOTORES:
        ruta = _SERVICES / f"{nombre}.py"
        permitidos = _ESCRITOR_LEGITIMO.get(ruta.name, set())
        sobrantes = [
            (linea, valor)
            for linea, valor in _literales_de_clasificacion(_arbol(ruta))
            if valor not in permitidos
        ]
        if sobrantes:
            fuera_de_contrato[nombre] = sobrantes
    assert fuera_de_contrato == {}, (
        "quedan literales de clasificación fuera del contrato (motor nº 5 en camino): "
        f"{fuera_de_contrato}"
    )


# ── Caso 3 ───────────────────────────────────────────────────────────────────

def test_03_el_contrato_es_puro_y_no_cierra_ciclos():
    """Que `gitlab_hierarchy` siga sin red, sin BD y sin config: es exactamente lo
    que hace que su test corra igual en los 3 runtimes y en CI sin red. Y que no
    importe a ninguno de los 4, o el import local de F2 sería un ciclo real."""
    importados = _modulos_importados(_arbol(_SERVICES / f"{_CONTRATO}.py"))

    ciclos = [m for m in importados if any(m.endswith(f".{n}") or m == n for n in _MOTORES)]
    assert ciclos == [], f"el contrato importa a uno de sus consumidores: {ciclos}"

    prohibidos = {"requests", "db", "config"}
    impuros = sorted(m for m in importados if m.split(".")[0] in prohibidos)
    assert impuros == [], f"el contrato dejó de ser puro: importa {impuros}"


# ── Caso 4 — el sembrado que hace que los 3 anteriores valgan ────────────────

def test_04_el_detector_marca_un_motor_nuevo_y_no_marca_un_docstring():
    """Sin este caso, los tres de arriba pasan porque el detector no busca nada."""
    motor_numero_cinco = (
        "def clasificar(labels):\n"
        "    is_epic = any('epic' in l for l in labels)\n"
        "    tipo = [l for l in labels if l.startswith('type::')]\n"
        "    padre = [l for l in labels if l.startswith('epic::')]\n"
        "    return is_epic, tipo, padre\n"
    )
    hallazgos = _literales_de_clasificacion(ast.parse(motor_numero_cinco))
    valores = sorted(v for _, v in hallazgos)
    assert valores == ["epic", "epic::", "type::"], (
        f"el detector NO ve un motor nº 5 escrito en su forma histórica: {hallazgos}"
    )

    # También lo ve cuando la etiqueta se compone con una f-string, que es como la
    # escribía `gitlab_provider._type_label` antes de este plan.
    con_fstring = "def etiqueta(t):\n    return f'type::{t}'\n"
    assert _literales_de_clasificacion(ast.parse(con_fstring)), (
        "una f-string esconde el literal al detector"
    )

    # NEGATIVO: si el detector descartara de más, daría cero hallazgos en los 4
    # módulos por el motivo equivocado. Acá el único texto sospechoso está en
    # docstrings —módulo Y función—, y no puede contar.
    solo_docstrings = (
        '"""Módulo que documenta type:: y epic:: sin usarlos."""\n'
        "def f():\n"
        '    """Devuelve el tipo del label type::X; el padre va en epic::<iid>."""\n'
        "    return None\n"
    )
    assert _literales_de_clasificacion(ast.parse(solo_docstrings)) == [], (
        "el detector cuenta docstrings: su número subiría al documentar el arreglo"
    )
