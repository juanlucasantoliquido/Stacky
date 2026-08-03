"""Plan 295 F3 — el detector de mentiras de la matriz cubre las TRANSVERSALES.

POR QUÉ EXISTE: test_matriz_no_miente_estructuralmente (test_plan218_capability_matrix
.py:107) recorre SOLO _CAPABILITY_TO_PORT_METHOD = 17 de las 71 claves. Las 54
restantes -- TLS, rate limit, webhooks, deep links, sync -- eran invisibles, y ahí
es donde el producto avanzó en la serie 276-292: el plan 295 F2 tuvo que corregir a
mano dos entradas que mentían desde entonces.

DISEÑO -- IMPORTACIÓN DINÁMICA EN EL TEST, NO EN EL MÓDULO. provider_capabilities
es PURO a propósito (su docstring :1-11 lo declara: sin red, sin DB, sin importar
adaptadores). El mapa nuevo guarda STRINGS; resolverlos es trabajo del test.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.provider_capabilities import (  # noqa: E402
    CAPABILITY_MATRIX,
    _CAPABILITY_TO_SYMBOL,
    capability_status,
)


def resolver_simbolo(ruta: str):
    """'services.gitlab_sync:sync_gitlab_tickets' -> el objeto, o None si no existe.

    Un módulo inexistente devuelve None (no explota): para una capacidad `absent`
    que apunta a un módulo que el plan siguiente va a crear, "no existe el módulo"
    y "no existe el símbolo" son el MISMO veredicto.
    """
    modulo, _, nombre = ruta.partition(":")
    assert nombre, f"ruta de símbolo sin ':' -> {ruta!r}"
    try:
        mod = importlib.import_module(modulo)
    except ModuleNotFoundError:
        return None
    return getattr(mod, nombre, None)


def test_el_mapa_no_esta_vacio_y_sus_claves_son_de_la_matriz():
    """Un mapa vacío haría pasar EN FALSO al gate de abajo (bucle de cero vueltas)."""
    assert len(_CAPABILITY_TO_SYMBOL) >= 5, f"solo {len(_CAPABILITY_TO_SYMBOL)} entradas"
    for capacidad, por_proveedor in _CAPABILITY_TO_SYMBOL.items():
        assert capacidad in CAPABILITY_MATRIX["gitlab"], f"{capacidad} no es clave de la matriz"
        assert por_proveedor, f"{capacidad} sin proveedores"
        for proveedor in por_proveedor:
            assert proveedor in CAPABILITY_MATRIX, f"proveedor desconocido: {proveedor}"


def test_el_mapa_cubre_al_menos_una_capacidad_sin_metodo_de_puerto():
    """El PUNTO de la fase: si todas las entradas ya estaban cubiertas por
    _CAPABILITY_TO_PORT_METHOD, este mapa no agrega nada y es un adorno."""
    from services.provider_capabilities import _CAPABILITY_TO_PORT_METHOD

    nuevas = set(_CAPABILITY_TO_SYMBOL) - set(_CAPABILITY_TO_PORT_METHOD)
    assert len(nuevas) >= 5, f"solo {len(nuevas)} capacidades transversales nuevas: {nuevas}"


def test_ningun_simbolo_se_repite_entre_capacidades():
    """[ADICIÓN ARQUITECTO 1 — Plan 295 F3, hallazgo C5 de la crítica v2]

    UN SÍMBOLO POR CAPACIDAD Y POR PROVEEDOR. Sin esto, el gate de abajo se
    convierte en ADORNO de la forma más fácil de cometer: apuntar varias
    capacidades al símbolo "grande" del módulo -- una clase de cliente, un
    `__init__`, un router -- que EXISTE SIEMPRE, cualquiera sea el estado real de
    la capacidad. El assert `obj is not None` pasa por construcción y el gate deja
    de vigilar sin dejar rastro: sigue verde, sigue contando para el KPI.

    Es exactamente lo que tenía el v1 de este plan: `tracker.sync.incremental` y
    `tracker.rate_limit.clamp` apuntaban las DOS a `services.ado_client:AdoClient`.

    La regla: dentro de un mismo proveedor, dos capacidades distintas NO pueden
    declarar el mismo `modulo:simbolo`. Si dos capacidades de verdad las resuelve
    el mismo símbolo, entonces son la MISMA capacidad y sobra una clave de la
    matriz -- que también es un hallazgo, y este test lo hace visible.
    """
    from collections import defaultdict

    por_proveedor: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for capacidad, por_prov in _CAPABILITY_TO_SYMBOL.items():
        for proveedor, ruta in por_prov.items():
            por_proveedor[proveedor][ruta].append(capacidad)

    repetidos = {
        f"{proveedor} -> {ruta}": sorted(caps)
        for proveedor, rutas in por_proveedor.items()
        for ruta, caps in rutas.items()
        if len(caps) > 1
    }
    assert not repetidos, (
        "un mismo símbolo vigila DOS capacidades distintas del mismo proveedor, así "
        "que el gate no puede fallar para ninguna de las dos (símbolo 'siempre existe'):\n"
        + "\n".join(f"  {k}: {v}" for k, v in sorted(repetidos.items()))
        + "\nAncla cada capacidad al símbolo que HACE ESE trabajo, no al del módulo."
    )


@pytest.mark.parametrize("capacidad", sorted(_CAPABILITY_TO_SYMBOL))
def test_el_status_declarado_coincide_con_la_existencia_del_simbolo(capacidad):
    """LAS DOS DIRECCIONES.

      full/partial => el símbolo EXISTE  (caza la matriz que subestima al proveedor)
      absent       => el símbolo NO existe (caza la matriz que quedó atrás cuando
                      el plan siguiente construyó la capacidad y no la declaró)
    """
    for proveedor, ruta in _CAPABILITY_TO_SYMBOL[capacidad].items():
        status = capability_status(proveedor, capacidad)
        obj = resolver_simbolo(ruta)
        if status in ("full", "partial"):
            assert obj is not None, (
                f"{proveedor}/{capacidad} declarado {status} pero {ruta} no existe. "
                "O la matriz miente, o el símbolo se renombró: arreglá el que esté mal."
            )
        elif status == "absent":
            assert obj is None, (
                f"{proveedor}/{capacidad} declarado ABSENT pero {ruta} YA EXISTE. "
                "Alguien construyó la capacidad y no actualizó la matriz: pasala a "
                "_f() con evidencia por SÍMBOLO."
            )
        # status 'n/a' no se opina: es una capacidad que no aplica al proveedor.
