"""pipeline_env_resolver.py — Plan 251 F3. Resolucion SOLO LECTURA.

Busca cada requerimiento en las fuentes que Stacky YA tiene, para no pedirle al
operador nada que ya exista. NO escribe en ningun lado. El VALOR de un secreto nunca
entra a este modulo: solo se consulta la EXISTENCIA de la key.

Vive aparte de `pipeline_environments.py` a proposito: ese modulo queda PURO para
siempre y su `test_f1_modulo_puro` no se vuelve fragil.
"""
from __future__ import annotations

from typing import Optional

import yaml

from services.pipeline_environments import (
    PROVIDER_ADO,
    _declared_variables,
    is_ado_predefined,
)

_MSG_ERROR_INTERNO = "Error interno al leer variables"


def list_scoped_variables(project: Optional[str] = None) -> tuple:
    """(variables, scopes, degradaciones). NUNCA propaga una excepcion cruda ni un
    mensaje que pueda traer datos del proveedor."""
    from services.ci_variables import (  # noqa: PLC0415
        VariablesUnavailableError,
        get_variables_provider,
    )

    try:
        provider = get_variables_provider(project)
    except VariablesUnavailableError:
        return [], (), ["ADO sin pipeline definition: no se pudieron leer variables del "
                        "proveedor (creala con 'Llevar a producción', plan 95)"]
    except Exception as e:
        return [], (), [_mensaje_seguro(e)]

    degradaciones: list = []
    scoped = getattr(provider, "list_variables_scoped", None)
    try:
        if callable(scoped):
            variables = list(scoped() or [])
        else:
            variables = [{**v, "environment_scope": "*"}
                         for v in (provider.list_variables() or [])]
            degradaciones.append(
                "el proveedor '%s' no expone alcance por entorno: todas las variables "
                "se consideran globales" % getattr(provider, "name", "?"))
    except VariablesUnavailableError:
        return [], (), ["ADO sin pipeline definition: no se pudieron leer variables del "
                        "proveedor (creala con 'Llevar a producción', plan 95)"]
    except Exception as e:
        return [], (), [_mensaje_seguro(e)]

    scopes = tuple(sorted({str(v.get("environment_scope") or "*")
                           for v in variables} - {"*"}))
    return variables, scopes, degradaciones


def _mensaje_seguro(e: Exception) -> str:
    """PROHIBIDO `str(e)` de una excepcion desconocida: puede traer el cuerpo de la
    respuesta del proveedor, y ahi puede venir un valor."""
    from services.tracker_provider import (  # noqa: PLC0415
        TrackerApiError,
        TrackerConfigError,
    )

    if isinstance(e, TrackerConfigError):
        return str(e)
    if isinstance(e, TrackerApiError):
        return ("El proveedor no respondió al listar variables (código %s)"
                % getattr(e, "status", "?"))
    return _MSG_ERROR_INTERNO


def _servidores() -> list:
    try:
        from services import server_registry  # noqa: PLC0415
        return list(server_registry.list_servers() or [])
    except Exception:
        return []


def resolve(requirements: tuple, environments: tuple, provider: str,
            project: Optional[str] = None, use_provider: bool = True,
            yaml_text: str = "") -> tuple:
    """(resolutions, degradaciones) para alimentar `build_matrix`.

    Con `use_provider=False` NO toca la red. Precedencia por celda, PRIMERA que acierta:
      1. parameter con declared_default   -> default / yaml_parameter_default
      2. predefinida de ADO               -> definido / predefinida
      3. declarada en `variables:`        -> definido / yaml_variables
      4. key en el proveedor              -> definido / caja_fuerte | scope_proveedor
      5. server que matchea el registro   -> definido / registro_servidores
      6. sin acierto                      -> sin entrada (build_matrix pone el default)
    """
    degradaciones: list = []
    variables: list = []
    if use_provider:
        variables, _scopes, degradaciones = list_scoped_variables(project)

    por_key: dict = {}
    for v in variables:
        key = str(v.get("key") or "")
        if key:
            por_key.setdefault(key, []).append(
                (str(v.get("environment_scope") or "*"), v.get("has_value")))

    declaradas: dict = {}
    if yaml_text:
        try:
            doc = yaml.safe_load(yaml_text)
        except yaml.YAMLError:
            doc = None
        if isinstance(doc, dict):
            declaradas = _declared_variables(doc)

    servidores = _servidores() if any(r.kind == "server" for r in requirements) else []

    resoluciones: dict = {}
    for req in requirements:
        for env in environments:
            entrada = _resolver_celda(req, env, provider, por_key, declaradas, servidores)
            if entrada is not None:
                resoluciones[(req.name, env)] = entrada
    return resoluciones, tuple(degradaciones)


def _elegir_entrada(entries: list, env: str):
    """(Plan 260) Una sola regla para los DOS proveedores: el scope EXACTO
    (case-insensitive) gana siempre que exista; "*" es el fallback. ADO nunca
    tiene mas de una entrada (list_variables_scoped fija environment_scope="*"
    siempre - ado_variables.py), asi que para ADO esto simplemente devuelve esa
    unica entrada por la rama de fallback. Orden INVERTIDO a proposito respecto
    del codigo pre-260 (que miraba "*" primero): antes de este plan el orden no
    importaba (mismo resultado los dos casos); ahora si, porque cada entrada
    trae su propio has_value (una key puede estar cargada en general y, a la
    vez, recien declarada vacia en un entorno especifico)."""
    comodin = None
    for scope, hv in entries:
        if scope == "*":
            comodin = (scope, hv)
        elif str(scope).lower() == str(env).lower():
            return (scope, hv)          # match exacto: gana siempre, sin excepcion
    return comodin                       # None si no hay ni exacto ni "*"


def _resolver_celda(req, env: str, provider: str, por_key: dict, declaradas: dict,
                    servidores: list):
    if req.kind == "parameter" and req.declared_default is not None:
        return ("default", "yaml_parameter_default", None)
    if provider == PROVIDER_ADO and is_ado_predefined(req.name):
        return ("definido", "predefinida", None)
    if req.kind in ("variable", "secret"):
        if req.name in declaradas or req.declared_default is not None:
            return ("definido", "yaml_variables", None)
        entradas = por_key.get(req.name)
        if entradas:
            elegida = _elegir_entrada(entradas, env)
            if elegida is None:
                return None
            _, hv = elegida
            if hv is True:
                fuente = "caja_fuerte" if provider == PROVIDER_ADO else (
                    "caja_fuerte" if elegida[0] == "*" else "scope_proveedor")
                return ("definido", fuente, None)
            if hv is False:
                return ("falta", "declarada_sin_valor",
                        "el nombre existe en el proveedor pero no tiene valor")
            return ("manual", "declarada_sin_valor_verificable",
                    "el proveedor no informa si este secreto tiene valor: verificalo vos")
    if req.kind == "server":
        objetivo = str(req.name or "").strip().lower()
        for s in servidores:
            alias = str(s.get("alias") or "").strip().lower()
            host = str(s.get("host") or "").strip().lower()
            if objetivo and objetivo in (alias, host):
                nota = ("credencial guardada" if s.get("has_password")
                        else "sin credencial guardada")
                return ("definido", "registro_servidores", nota)
    return None
