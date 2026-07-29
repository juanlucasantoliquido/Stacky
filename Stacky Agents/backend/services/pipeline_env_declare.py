"""pipeline_env_declare.py — Plan 260 F2. Núcleo PURO del plan de declaración.

Decide, sin red y sin I/O, qué nombres de variable/secreto declarar (con valor
VACÍO) en el proveedor y cuáles saltar, y por qué. `services/pipeline_environments.py`
(Plan 251) queda intacto: este módulo vive aparte, a propósito.

Declarar un nombre NO es cargar un valor: el `DeclareItem` nunca lleva un valor,
solo el nombre, si es secreto, y por qué se declara.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from services.ci_variables import validate_variable_key
from services.pipeline_environments import PROVIDER_ADO, PROVIDER_GITLAB

# Motivos fijos por kind NO declarable (§4.2).
_MOTIVO_POR_KIND = {
    "server": "no es una variable: se carga en el registro de servidores (Plan 91)",
    "deploy_path": "es una ruta, no una variable de pipeline",
    "service_connection": "se crea en la UI del proveedor, no por API de variables",
    "parameter": "tiene default en el YAML o se elige al encolar",
}
_KINDS_DECLARABLES = ("variable", "secret")

_NOTA_MASKING_GITLAB = (
    "al cargar el valor, marca la casilla 'secreta': si no la marcas, GitLab va "
    "a mostrar el valor sin enmascarar en el log del job"
)


@dataclass(frozen=True)
class DeclareItem:
    key: str            # nombre a crear en el proveedor
    secret: bool        # is_secret del requirement, en AMBOS proveedores (§3.6)
    reason: str         # por que se declara (kind + entorno donde falta)
    note: str           # que tiene que hacer el operador despues


@dataclass(frozen=True)
class DeclarePlan:
    items: tuple        # tuple[DeclareItem, ...], orden determinista (por key)
    skipped: tuple       # tuple[(key, motivo), ...] — lo que NO se declara y por que
    provider: str


def proyectar_has_value(provider: str, es_secreto: bool) -> object:
    """Que va a devolver el proveedor DESPUES de declarar la key con valor vacio.
    UNICA fuente de verdad de la proyeccion (ADICION 3). ADO+secreto -> None
    (isSecret=true => value:null => DESCONOCIDO); el resto -> False (el
    proveedor confirma el vacio). Lo prueba, fila por fila,
    tests/plan260_corpus/declare_matrix.json."""
    if provider == PROVIDER_ADO and es_secreto:
        return None
    return False


def plan_declaration(matrix, provider: str) -> DeclarePlan:
    """(matrix, provider) -> DeclarePlan. Determinista: misma entrada, misma
    salida, mismo orden (por key). Solo mira celdas `state == "falta"`: el
    resto (definido/default/manual) no necesita declararse — o ya tiene
    valor, o Stacky no sabe si le falta (no se le pide al operador de mas)."""
    reqs_by_name = {r.name: r for r in matrix.requirements}

    entornos_por_requirement: dict = {}
    for cell in matrix.cells:
        if cell.state == "falta":
            entornos_por_requirement.setdefault(cell.requirement, []).append(cell.environment)

    items: list = []
    skipped: list = []
    for name in sorted(entornos_por_requirement):
        req = reqs_by_name.get(name)
        if req is None:
            continue

        motivo_kind = _MOTIVO_POR_KIND.get(req.kind)
        if motivo_kind is not None:
            skipped.append((name, motivo_kind))
            continue
        if req.kind not in _KINDS_DECLARABLES:
            skipped.append((name, "tipo de requerimiento no declarable"))
            continue

        error_key = validate_variable_key(name)
        if error_key is not None:
            skipped.append((name, error_key))
            continue

        envs = sorted(entornos_por_requirement[name])
        reason = "%s falta en: %s" % (req.kind, ", ".join(envs))
        note = _NOTA_MASKING_GITLAB if (provider == PROVIDER_GITLAB and req.is_secret) else ""

        items.append(DeclareItem(key=name, secret=bool(req.is_secret), reason=reason, note=note))

    return DeclarePlan(items=tuple(items), skipped=tuple(skipped), provider=provider)


def pendiente_visible(cells) -> int:
    """(§4.1) Formula UNICA de conteo visible: celdas 'falta' + celdas 'manual'
    cuyo source sea 'declarada_sin_valor_verificable' (ADO+secreto declarado).
    `pending_count` (contrato del 251) NO se toca: cuenta SOLO 'falta'."""
    total = 0
    for c in cells:
        if c.state == "falta":
            total += 1
        elif c.state == "manual" and c.source == "declarada_sin_valor_verificable":
            total += 1
    return total


def proyectar_celdas(cells, plan: DeclarePlan) -> tuple:
    """(ADICIÓN ARQUITECTO 3) Cómo quedarían las celdas DESPUES de declarar el
    plan, SIN escribir nada: proyecta, para cada celda 'falta' con un
    DeclareItem, el has_value que el proveedor va a confirmar (proyectar_has_value)
    y el (state, source) que le correspondería según la MISMA tabla de verdad
    que usa el resolver real. Celdas no declaradas (skip, u otro estado) viajan
    sin tocar."""
    declaradas = {item.key: item for item in plan.items}
    proyectadas = []
    for cell in cells:
        item = declaradas.get(cell.requirement)
        if cell.state == "falta" and item is not None:
            hv = proyectar_has_value(plan.provider, item.secret)
            if hv is False:
                proyectadas.append(replace(cell, state="falta", source="declarada_sin_valor"))
            else:  # None — ADO+secreto: el proveedor no puede confirmar el vacio
                proyectadas.append(replace(cell, state="manual",
                                           source="declarada_sin_valor_verificable"))
        else:
            proyectadas.append(cell)
    return tuple(proyectadas)
