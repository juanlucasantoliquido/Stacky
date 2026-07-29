"""api/setup_guide.py - Guia de configuracion verificable (Plan 259).

url_prefix="/setup-guide" -> rutas /api/setup-guide/... (NO poner /api/ en el
prefix: `api_bp` de api/__init__.py:84 ya aporta el /api).

=============================================================================
STUB CREADO POR LA COSTURA P0 (2026-07-28). CERO RUTAS A PROPOSITO.
-----------------------------------------------------------------------------
Existe unicamente para que `api/__init__.py` pueda registrar este blueprint
AHORA, sin que el arranque explote con ImportError, y asi el paquete P2 (plan
259) no tenga que editar `api/__init__.py` -- que es un archivo compartido con
el paquete P3 (plan 267).

DUENO EXCLUSIVO: el paquete P2 / plan 259. Llena este archivo con sus 2 rutas
(F4.b del plan):
    GET  /api/setup-guide/<provider>
    POST /api/setup-guide/gitlab/verify
NO hace falta tocar `api/__init__.py`: el import y el register_blueprint YA ESTAN.

OJO -- ESTO NO SALIO DEL PLAN, SE DERIVO (el plan 259 no declara ni el nombre
del Blueprint, ni la variable, ni el url_prefix; `url_prefix` aparece 0 veces en
sus 2299 lineas). Se derivo de las URLs finales que el plan SI especifica mas la
convencion de la casa (`bp`, y el prefix sin /api). Si el plan 259 acaba
declarando otro prefix, este es el lugar para cambiarlo -- pero entonces hay que
cambiarlo tambien en el frontend.

TRAMPA que el criterio binario del propio plan NO detecta: F4 verifica que
`app.url_map` contenga "setup-guide" filtrando por esa cadena. Con el prefix mal
puesto las rutas quedan en /api/api/setup-guide/... y ese filtro PASA IGUAL,
porque la cadena "setup-guide" sigue presente. Verificar la ruta COMPLETA.
=============================================================================
"""
from __future__ import annotations

from flask import Blueprint

bp = Blueprint("setup_guide", __name__, url_prefix="/setup-guide")

# Sin rutas todavia: las agrega el plan 259 (paquete P2).
