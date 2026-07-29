"""api/devops_actions.py - Catalogo de acciones DevOps (Plan 267).

url_prefix="/devops/actions" -> rutas /api/devops/actions/... (NO poner /api/ en el
prefix; mismo gotcha C2 del plan 73, ver api/devops_agent.py:3-4).

=============================================================================
STUB CREADO POR LA COSTURA P0 (2026-07-28). CERO RUTAS A PROPOSITO.
-----------------------------------------------------------------------------
Existe unicamente para que `api/__init__.py` pueda registrar este blueprint
AHORA, sin que el arranque explote con ImportError, y asi el paquete P3 (plan
267) no tenga que editar `api/__init__.py` -- que es un archivo compartido con
el paquete P2 (plan 259).

DUENO EXCLUSIVO: el paquete P3 / plan 267. Llena este archivo con sus rutas
(F1 del plan). NO hace falta tocar `api/__init__.py`: el import y el
register_blueprint YA ESTAN.

La linea del Blueprint es copia LITERAL del plan 267 (doc :871). No la cambies:
el nombre "devops_actions" y el prefix "/devops/actions" son contrato.
=============================================================================
"""
from __future__ import annotations

from flask import Blueprint

bp = Blueprint("devops_actions", __name__, url_prefix="/devops/actions")

# Sin rutas todavia: las agrega el plan 267 (paquete P3).
