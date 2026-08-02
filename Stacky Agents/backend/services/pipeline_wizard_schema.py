"""services/pipeline_wizard_schema.py — Plan 294 F4.

Las preguntas del paso 3 del asistente salen de DATOS, no de `if`s: agregar un
tipo de pipeline es agregar una entrada a una tupla, no reescribir el asistente.

MODULO PURO. No lee archivos, no barre directorios, no habla por red. Todo lo
que hace es filtrar tuplas declaradas aca.

R9 — "no se pregunta lo que Stacky puede averiguar": toda pregunta declara
`autofilled_from`, y si el sondeo del paso 1 ya trajo ese dato la pregunta se
OMITE. Esa es la diferencia entre un asistente y un formulario.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WizardGoal:
    id: str
    label: str
    help: str
    example: str
    pipeline_kind: str                 # "ci" | "cd" | "ci_cd" | "quality"
    needs_inventory: bool = False      # True SOLO para "modificar_existente"


@dataclass(frozen=True)
class WizardQuestion:
    id: str
    label: str
    help: str
    example: str
    kind: str                          # "text" | "choice" | "bool" | "multi"
    options: tuple[str, ...] = ()
    default: str = ""
    required: bool = True
    depends_on: tuple[tuple[str, str], ...] = ()   # (id_de_pregunta, valor) — AND
    autofilled_from: str = ""          # clave del sondeo que la resuelve sola (R9)


WIZARD_GOALS: tuple[WizardGoal, ...] = (
    WizardGoal(
        id="compilar_validar",
        label="Compilar y validar que el codigo arma",
        help="Cada vez que alguien sube un cambio, se compila para saber si rompio algo.",
        example="Compilar la solucion y avisar si no arma.",
        pipeline_kind="ci",
    ),
    WizardGoal(
        id="ejecutar_tests",
        label="Correr las pruebas automaticas",
        help="Se ejecutan las pruebas del proyecto y se avisa si alguna falla.",
        example="Correr las pruebas en cada cambio de la rama principal.",
        pipeline_kind="ci",
    ),
    WizardGoal(
        id="generar_artefacto",
        label="Generar el paquete que se instala",
        help="Se arma el paquete o la carpeta lista para instalar y se guarda un tiempo.",
        example="Dejar la carpeta publicada lista para descargar.",
        pipeline_kind="ci",
    ),
    WizardGoal(
        id="desplegar",
        label="Instalar en un ambiente",
        help="Se lleva lo ya construido a un ambiente concreto, con tu aprobacion.",
        example="Publicar la version aprobada en el ambiente de pruebas.",
        pipeline_kind="cd",
    ),
    WizardGoal(
        id="ci_completo",
        label="Compilar y probar en un solo paso",
        help="Junta compilar y correr las pruebas, y opcionalmente guarda el paquete.",
        example="Compilar, probar y guardar el resultado en cada cambio.",
        pipeline_kind="ci",
    ),
    WizardGoal(
        id="entrega_completa",
        label="De compilar hasta instalar",
        help="Todo el recorrido: compilar, probar, empaquetar e instalar en un ambiente.",
        example="De un cambio en la rama principal hasta el ambiente de pruebas.",
        pipeline_kind="ci_cd",
    ),
    WizardGoal(
        id="calidad_seguridad",
        label="Revisar calidad o seguridad",
        help="Se pasa una revision automatica y se decide si avisa o si frena el cambio.",
        example="Revisar dependencias con problemas conocidos y avisar.",
        pipeline_kind="quality",
    ),
    WizardGoal(
        id="modificar_existente",
        label="Cambiar una pipeline que ya tenes",
        help="Se parte de una de las que ya existen y se le hace un cambio puntual.",
        example="Agregarle el paso de pruebas a la que hoy solo compila.",
        pipeline_kind="ci",
        needs_inventory=True,
    ),
    WizardGoal(
        id="describir_libre",
        label="Contarlo con tus palabras",
        help="Describis lo que necesitas y el asistente propone un borrador para revisar.",
        example="'Quiero que cada noche corra todo y me avise si algo fallo.'",
        pipeline_kind="ci",
    ),
)

_GOALS_BY_ID: dict[str, WizardGoal] = {g.id: g for g in WIZARD_GOALS}

# ─────────────────────────────────────────────────────────── banco de preguntas
# Cada pregunta se declara UNA vez y se referencia por id desde el mapa de abajo.

_Q: dict[str, WizardQuestion] = {
    "build_command": WizardQuestion(
        id="build_command",
        label="Con que comando se compila",
        help="El comando que usas hoy en tu maquina para compilar el proyecto.",
        example="dotnet build",
        kind="text",
        autofilled_from="build_command",
    ),
    "test_command": WizardQuestion(
        id="test_command",
        label="Con que comando se prueba",
        help="El comando que corre las pruebas del proyecto.",
        example="dotnet test",
        kind="text",
        autofilled_from="test_command",
    ),
    "coverage": WizardQuestion(
        id="coverage",
        label="Queres guardar el informe de cobertura",
        help="Es el resumen de cuanto codigo tocan las pruebas.",
        example="Si",
        kind="bool",
        default="no",
        required=False,
    ),
    "branches": WizardQuestion(
        id="branches",
        label="En que ramas se ejecuta",
        help="Las ramas cuyo cambio dispara esta automatizacion.",
        example="main",
        kind="text",
        default="main",
        autofilled_from="default_branch",
    ),
    "artifact_path": WizardQuestion(
        id="artifact_path",
        label="Que carpeta se guarda",
        help="La carpeta con el resultado que queres conservar.",
        example="publish",
        kind="text",
    ),
    "artifact_retention": WizardQuestion(
        id="artifact_retention",
        label="Cuantos dias se conserva",
        help="Pasado ese plazo el paquete se borra solo.",
        example="30",
        kind="text",
        default="30",
        required=False,
    ),
    "deploy_environment": WizardQuestion(
        id="deploy_environment",
        label="A que ambiente se instala",
        help="El ambiente destino, tal como lo llaman en tu equipo.",
        example="pruebas",
        kind="text",
    ),
    "deploy_target": WizardQuestion(
        id="deploy_target",
        label="Donde queda instalado",
        help="El servidor, sitio o destino concreto donde queda la version.",
        example="servidor de pruebas",
        kind="text",
    ),
    "deploy_approval": WizardQuestion(
        id="deploy_approval",
        label="Hace falta que alguien apruebe",
        help="Si esta en si, la instalacion espera una aprobacion antes de correr.",
        example="Si",
        kind="bool",
        default="si",
    ),
    "quality_check": WizardQuestion(
        id="quality_check",
        label="Que se revisa",
        help="El tipo de revision automatica que queres pasar.",
        example="dependencias con problemas conocidos",
        kind="choice",
        options=("dependencias", "estilo_de_codigo", "secretos_en_el_codigo"),
    ),
    "quality_blocking": WizardQuestion(
        id="quality_blocking",
        label="Si encuentra algo, frena o solo avisa",
        help="Frenar impide seguir; avisar deja pasar el cambio con una advertencia.",
        example="avisa",
        kind="choice",
        options=("frena", "avisa"),
        default="avisa",
    ),
    "existing_pipeline": WizardQuestion(
        id="existing_pipeline",
        label="Cual de las que ya tenes",
        help="Se elige de la lista que el asistente detecto en el paso 1.",
        example="azure-pipelines.yml",
        kind="choice",
        autofilled_from="existing_pipeline_key",
    ),
    "change_description": WizardQuestion(
        id="change_description",
        label="Que le queres cambiar",
        help="Contalo con tus palabras; el asistente propone el cambio para revisar.",
        example="que ademas corra las pruebas",
        kind="text",
    ),
    "free_text": WizardQuestion(
        id="free_text",
        label="Contanos que necesitas",
        help="Describilo como se lo contarias a un companero. No hace falta ser tecnico.",
        example="Quiero que cada noche corra todo y me avise si algo fallo.",
        kind="text",
    ),
    "needs_docker": WizardQuestion(
        id="needs_docker",
        label="Se publica como contenedor",
        help="Solo si tu equipo distribuye la aplicacion como imagen de contenedor.",
        example="No",
        kind="bool",
        default="no",
        required=False,
    ),
    "docker_registry": WizardQuestion(
        id="docker_registry",
        label="A que registro se sube la imagen",
        help="El lugar donde tu equipo guarda las imagenes.",
        example="registro interno",
        kind="text",
        depends_on=(("needs_docker", "si"),),
    ),
    "docker_tag": WizardQuestion(
        id="docker_tag",
        label="Con que etiqueta",
        help="El nombre de version que lleva la imagen.",
        example="latest",
        kind="text",
        default="latest",
        required=False,
        depends_on=(("needs_docker", "si"),),
    ),
}

#: Mapa CERRADO objetivo -> ids de pregunta, EN ORDEN. Agregar un objetivo es
#: agregar una fila aca, no escribir un `if`.
_QUESTIONS_BY_GOAL: dict[str, tuple[str, ...]] = {
    "compilar_validar": ("build_command", "branches"),
    "ejecutar_tests": ("test_command", "coverage", "branches"),
    "generar_artefacto": ("build_command", "artifact_path", "artifact_retention"),
    "desplegar": (
        "deploy_environment", "deploy_target", "deploy_approval",
        "needs_docker", "docker_registry", "docker_tag",
    ),
    "ci_completo": ("build_command", "test_command", "branches"),
    "entrega_completa": (
        "build_command", "test_command", "deploy_environment", "deploy_approval",
    ),
    "calidad_seguridad": ("quality_check", "quality_blocking", "branches"),
    "modificar_existente": ("existing_pipeline", "change_description"),
    "describir_libre": ("free_text",),
}

#: Defaults SEGUROS por stack. Si no hay senal, cadena vacia: nunca se inventa.
_DEFAULTS_BY_STACK: dict[str, dict[str, str]] = {
    "python": {"build_command": "pip install -r requirements.txt", "test_command": "pytest"},
    "node": {"build_command": "npm run build", "test_command": "npm test"},
    "dotnet": {"build_command": "dotnet build", "test_command": "dotnet test"},
}


def questions_for(
    goal: str,
    *,
    stack: str = "",
    provider: str = "",
    has_docker: bool = False,
    known: dict | None = None,
) -> tuple[WizardQuestion, ...]:
    """Preguntas del paso 3 para un objetivo. PURA.

    `known` son los datos que el sondeo del paso 1 YA trajo: toda pregunta cuyo
    `autofilled_from` este en `known` con valor no vacio se OMITE (R9).
    Un objetivo desconocido devuelve la tupla vacia; quien decide si eso es un
    error es el llamador (el endpoint responde 400).
    """
    ids = _QUESTIONS_BY_GOAL.get(goal)
    if not ids:
        return ()

    resueltos = {
        str(k): str(v)
        for k, v in (known or {}).items()
        if str(v or "").strip()
    }
    _ = (stack, provider, has_docker)  # el filtrado por stack vive en default_answers

    out: list[WizardQuestion] = []
    vistos: set[str] = set()
    for qid in ids:
        q = _Q.get(qid)
        if q is None or q.id in vistos:
            continue
        if q.autofilled_from and q.autofilled_from in resueltos:
            continue           # R9: Stacky ya lo sabe, no se pregunta
        vistos.add(q.id)
        out.append(q)
    return tuple(out)


def visible_questions(qs, answers: dict) -> tuple[WizardQuestion, ...]:
    """Filtra por `depends_on` (AND de pares (id, valor)). PURA."""
    respuestas = {str(k): str(v) for k, v in (answers or {}).items()}
    out: list[WizardQuestion] = []
    for q in qs or ():
        if all(respuestas.get(dep_id) == dep_val for dep_id, dep_val in q.depends_on):
            out.append(q)
    return tuple(out)


def default_answers(goal: str, stack: str, provider: str) -> dict:
    """Defaults seguros por stack. Sin senal, cadena vacia: nunca se inventa."""
    base = dict(_DEFAULTS_BY_STACK.get((stack or "").strip().lower(), {}))
    meta = _GOALS_BY_ID.get(goal)
    out: dict[str, str] = {}
    for qid in _QUESTIONS_BY_GOAL.get(goal, ()):
        q = _Q.get(qid)
        if q is None:
            continue
        out[q.id] = base.get(q.id, q.default)
    if meta is not None:
        out["pipeline_kind"] = meta.pipeline_kind
    out["provider"] = (provider or "").strip().lower()
    return out
