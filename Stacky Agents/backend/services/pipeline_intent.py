"""services/pipeline_intent.py — Plan 294 F3. El contrato `PipelineIntent`.

QUE ES. El objeto declarativo que el asistente guiado llena paso a paso y que se
traduce a lo que el generador (plan 73) YA sabe leer. El asistente NO renderiza
archivos: `intent_to_spec` es el UNICO puente hacia `services.pipeline_spec`.

MODULO PURO. No importa red, no importa cliente de proveedor y no llama a ningun
modelo. Todo lo que hace es traducir estructuras.

R3 (riel duro). `variables` y `required_secrets` llevan NOMBRES, jamas valores.
`intent_to_dict` lanza ValueError si un elemento trae "=" o ":": esa es
exactamente la forma en que un valor se cuela en una lista de nombres.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields

INTENT_SCHEMA_VERSION: str = "1"

#: Los 3 ids REALES del selector de runtime. Espejan COPILOT_RUNTIMES de
#: frontend/src/components/devops/pipelineCopilotModel.ts y el tipo
#: CopilotRuntimeId. Los strings sueltos que NO existen en el codigo son los que
#: un plan viejo invento; usar cualquiera de esos es un defecto.
WIZARD_RUNTIME_IDS: tuple[str, ...] = ("claude_code_cli", "codex_cli", "github_copilot")

#: Vocabulario cerrado del tipo de pipeline.
PIPELINE_KINDS: tuple[str, ...] = ("ci", "cd", "ci_cd", "quality")

#: Mapeo CERRADO paso del asistente -> estado canonico de pipeline_session.
#: NO es una segunda maquina de estados: es la proyeccion de las pantallas sobre
#: la maquina que YA existe (plan 279). Su totalidad y la legalidad de cada salto
#: contra TRANSITIONS las verifica un test; sin eso, "reusamos el 279" seria prosa.
WIZARD_STEP_TO_STATE: dict[str, str] = {
    "p1": "discovery",
    "p2": "discovery",
    "p3": "discovery",
    "p4": "discovery",
    "p5": "draft",
    "p6": "review",   # el frontend puede mostrar "secrets" si faltan variables;
                      # la transicion review->secrets YA es legal en TRANSITIONS
    "p7": "confirm",  # confirm -> committed | failed, ya en TRANSITIONS
}


@dataclass(frozen=True)
class PipelineIntent:
    """Intencion estructurada. Serializable a JSON puro. 24 campos."""

    schema_version: str = INTENT_SCHEMA_VERSION   # aditivo: nunca se rompe, se sube
    project: str = ""
    repository: str = ""
    provider: str = ""                 # "ado" | "gitlab" (vocabulario de PIPELINE_FILENAME)
    default_branch: str = ""
    stack: str = ""                    # "python" | "node" | "dotnet" | ""
    framework: str = ""
    package_manager: str = ""
    goal: str = ""                     # una de WIZARD_GOALS
    pipeline_kind: str = ""            # "ci" | "cd" | "ci_cd" | "quality"
    triggers: tuple[str, ...] = ()     # ramas
    stages: tuple[str, ...] = ()
    build_command: str = ""
    test_command: str = ""
    coverage: bool = False
    artifacts: tuple[str, ...] = ()
    environments: tuple[str, ...] = ()
    deploy_target: str = ""
    variables: tuple[str, ...] = ()          # NOMBRES. JAMAS valores.
    required_secrets: tuple[str, ...] = ()   # NOMBRES. JAMAS valores.
    runtime: str = ""                        # uno de WIZARD_RUNTIME_IDS
    constraints: tuple[str, ...] = ()
    existing_pipeline_key: str = ""    # clave del inventario (pipeline_inventory.identity_key)
    free_text: str = ""


_FIELD_NAMES: tuple[str, ...] = tuple(f.name for f in fields(PipelineIntent))
_TUPLE_FIELDS: frozenset[str] = frozenset(
    f.name for f in fields(PipelineIntent) if f.type == "tuple[str, ...]"
)

#: Un NOMBRE de variable o de secreto no puede traer estos caracteres: son la
#: firma de que alguien pego "NOMBRE=valor" o "NOMBRE: valor".
_MARCAS_DE_VALOR: tuple[str, ...] = ("=", ":")


def _tupla(valor) -> tuple[str, ...]:
    if valor is None:
        return ()
    if isinstance(valor, (str, bytes)):
        return (str(valor),)
    try:
        return tuple(str(v) for v in valor)
    except TypeError:
        return ()


def _proposed_path(provider: str) -> str:
    """Sale de pipeline_session.PIPELINE_FILENAME. NO se hardcodea el nombre."""
    from services.pipeline_session import PIPELINE_FILENAME   # noqa: PLC0415

    return PIPELINE_FILENAME.get((provider or "").strip().lower(), "")


def intent_from_dict(d: dict | None) -> PipelineIntent:
    """dict -> PipelineIntent. TOLERANTE: un campo desconocido se IGNORA.

    `proposed_path` se deriva del `provider`, asi que viene calculado en
    `intent_to_dict` pero no es un campo del dataclass: entra por la puerta de
    los desconocidos y se descarta, que es justo lo que hace el round-trip exacto.
    """
    origen = d if isinstance(d, dict) else {}
    kwargs: dict = {}
    for nombre in _FIELD_NAMES:
        if nombre not in origen:
            continue
        crudo = origen[nombre]
        if nombre in _TUPLE_FIELDS:
            kwargs[nombre] = _tupla(crudo)
        elif nombre == "coverage":
            kwargs[nombre] = bool(crudo)
        else:
            kwargs[nombre] = "" if crudo is None else str(crudo)
    return PipelineIntent(**kwargs)


def intent_to_dict(i: PipelineIntent) -> dict:
    """PipelineIntent -> dict JSON puro, con `proposed_path` derivado.

    R3: lanza ValueError si algun NOMBRE de `variables` o `required_secrets`
    contiene "=" o ":". Es el punto exacto donde un valor se colaria al archivo.
    """
    for campo in ("variables", "required_secrets"):
        for nombre in getattr(i, campo):
            for marca in _MARCAS_DE_VALOR:
                if marca in str(nombre):
                    raise ValueError(
                        f"{campo} lleva NOMBRES, nunca valores: {nombre!r} contiene "
                        f"{marca!r}. Carga el valor en la caja fuerte de variables."
                    )
    out = asdict(i)
    for nombre in _TUPLE_FIELDS:
        out[nombre] = list(out[nombre])
    out["proposed_path"] = _proposed_path(i.provider)
    return out


def intent_to_spec(i: PipelineIntent) -> dict:
    """PipelineIntent -> dict que `services.pipeline_spec.dict_to_spec` acepta.

    Puente de `variables`, EXACTO y no inferido: `PipelineSpec.variables` es un
    `dict` mientras que `PipelineIntent.variables` es una tupla de NOMBRES.
    La cadena vacia es a proposito: el nombre viaja al archivo, el valor NUNCA.
    `required_secrets` NO entra al spec: viaja aparte, solo para el aviso
    "te falta cargar X" del paso de revision.
    """
    etapas: list[dict] = []

    if i.build_command.strip():
        etapas.append({
            "name": "build",
            "jobs": [{
                "name": "build",
                "steps": [{"name": "compilar", "script": i.build_command.strip()}],
            }],
        })
    if i.test_command.strip():
        etapas.append({
            "name": "test",
            "jobs": [{
                "name": "test",
                "steps": [{"name": "probar", "script": i.test_command.strip()}],
            }],
        })
    if not etapas:
        # Un spec sin etapas es invalido para el generador. Antes que emitir algo
        # que no valida, se declara una etapa honesta con el comando que haya.
        etapas.append({
            "name": "ci",
            "jobs": [{
                "name": "ci",
                "steps": [{"name": "paso", "script": "echo sin comando declarado"}],
            }],
        })

    return {
        "name": (i.project or i.repository or "pipeline").strip() or "pipeline",
        "stages": etapas,
        "variables": {nombre: "" for nombre in i.variables},
        "trigger_branches": list(i.triggers),
    }


def validate_intent(i: PipelineIntent) -> list[str]:
    """Motivos EN CASTELLANO por los que la intencion todavia no sirve.
    Lista vacia = esta lista para armar el borrador."""
    motivos: list[str] = []

    if not i.goal.strip():
        motivos.append("Falta elegir que queres lograr con esta pipeline.")
    if i.goal == "modificar_existente" and not i.existing_pipeline_key.strip():
        motivos.append(
            "Elegiste modificar una pipeline que ya existe, pero no indicaste cual "
            "de las del inventario."
        )
    if i.provider and i.provider not in ("ado", "gitlab"):
        motivos.append(
            f"No reconozco el proveedor {i.provider!r}: se admiten 'ado' y 'gitlab'."
        )
    if i.pipeline_kind and i.pipeline_kind not in PIPELINE_KINDS:
        motivos.append(
            f"No reconozco el tipo de pipeline {i.pipeline_kind!r}: "
            f"se admiten {', '.join(PIPELINE_KINDS)}."
        )
    if i.runtime and i.runtime not in WIZARD_RUNTIME_IDS:
        motivos.append(
            f"No reconozco el runtime {i.runtime!r}: se admiten "
            f"{', '.join(WIZARD_RUNTIME_IDS)}."
        )
    for campo, etiqueta in (("variables", "variables"), ("required_secrets", "secretos")):
        for nombre in getattr(i, campo):
            if any(m in str(nombre) for m in _MARCAS_DE_VALOR):
                motivos.append(
                    f"En la lista de {etiqueta} pusiste {nombre!r}, que parece traer "
                    f"un valor. Ahi van solo los nombres."
                )
    return motivos
