"""Plan 267 F0 — Catalogo unico de acciones DevOps.

PURO: sin flask, sin config, sin IO, sin red. Solo dataclasses + datos + lookups.
Es la fuente de VERDAD de la identidad y la seguridad de una accion; el COMO se
ejecuta vive en el binding del frontend (services/devopsActionBindings.ts), que
reusa los endpoints que ya existen. El ratchet de F8 exige igualdad de conjuntos.
"""
from __future__ import annotations

from dataclasses import dataclass

CATALOG_VERSION = "1"

EFFECTS = ("read", "write")
IMPACTS = ("none", "low", "high")
PARAM_TYPES = ("string", "int", "bool", "enum")
# v2 [C5] — desde donde puede DISPARARSE una accion (ver §4.10). Invariante
# I-REACH, verificada por el ratchet de F8: effect == "write" => "palette-run"
# NO puede estar en reach. El doble cerrojo de entityActions.ts:44-46, elevado
# a dato y cubriendo las TRES superficies en vez de una.
REACHES = ("button", "palette-run", "palette-nav", "assistant")

# v3 [C23] — `reach` se DERIVA de `effect`; NO se escribe a mano en las 23
# entradas. Asi I-REACH es cierta POR CONSTRUCCION (la unica tupla que contiene
# "palette-run" es la de lectura) y no queda una superficie de deriva de 23
# tuplas literales para que ~10 tests la patrullen.
REACH_READ = ("button", "palette-run", "assistant")
REACH_WRITE = ("button", "palette-nav", "assistant")


def canonical_reach(effect: str) -> tuple[str, ...]:
    """Unica fuente de `reach`. NUNCA lanza: cualquier valor distinto de
    "write" se trata como lectura para no explotar, y quien caza un `effect`
    invalido es test_effect_e_impact_en_vocabulario (F0 test 4)."""
    return REACH_WRITE if effect == "write" else REACH_READ


# Master del panel DevOps (api/devops.py::_health_payload, key "flag_enabled").
# Si esta en False, el panel no existe para el operador y ninguna accion de
# seccion es alcanzable [C6].
MASTER_HEALTH_KEY = "flag_enabled"

# Espejo CONGELADO de los ids de DEVOPS_SECTIONS (frontend/src/pages/DevOpsPage.tsx).
# El ratchet de F8 lo compara contra el archivo .tsx real: si el frontend agrega o
# renombra una seccion y no se actualiza aca, el test sale ROJO.
DEVOPS_SECTION_IDS = (
    "resumen", "pipelines", "publicaciones", "ambientes", "agente", "servidores",
    "variables", "remote-console", "pr-review", "despliegues", "taller-compilacion",
    "publicador-soluciones", "inventario-pipelines", "pipeline-audit",
    "editar-pipeline", "matriz-entornos", "paquete-entrega",
)


@dataclass(frozen=True)
class ActionParam:
    name: str                       # snake_case, unico dentro de la accion
    type: str                       # uno de PARAM_TYPES
    label: str                      # espanol, para la UI
    required: bool = False
    enum_values: tuple[str, ...] = ()   # obligatorio y no vacio si type == "enum"
    default: str = ""               # "" = sin default


@dataclass(frozen=True)
class DevOpsAction:
    id: str                         # "devops.<dominio>.<verbo>", unico
    label: str                      # espanol, imperativo corto ("Disparar pipeline")
    summary: str                    # 1 frase: que hace, para la tarjeta de preview
    section_id: str | None          # id de DEVOPS_SECTION_IDS, o None si vive fuera
    nav_path: str                   # deep-link donde el operador la ve manualmente
    effect: str                     # "read" | "write"
    impact: str                     # "none" | "low" | "high"
    targets_environment: bool       # True si actua sobre un entorno concreto
    health_key: str                 # key de _health_payload(), "" = siempre visible
    flag_key: str                   # key de la FlagSpec que la gatea, "" = ninguna
    reach: tuple[str, ...]          # v3 [C23] — SIEMPRE canonical_reach(effect)
    params: tuple[ActionParam, ...] = ()
    phrases: tuple[str, ...] = ()   # frases de intencion (matcher determinista)


# --------------------------------------------------------------------------
# Params reusados por las 23 entradas. `PRJ` es el PRIMER param de todas.
# --------------------------------------------------------------------------
PRJ = ActionParam(name="project", type="string", label="Proyecto", required=True)
ENV = ActionParam(
    name="environment",
    type="enum",
    label="Entorno",
    required=True,
    enum_values=("dev", "qa", "uat", "prod"),
)


# --------------------------------------------------------------------------
# Catalogo semilla — 23 acciones.
#
# `label`, `summary` y `phrases` son LITERALES del plan 267 F0 [C3, C24]: no se
# inventan, no se reordenan, no se traducen.
#
# `reach` va SIEMPRE por canonical_reach(<el mismo string que effect>) [C23];
# NUNCA una tupla literal. El t17b de F0 caza a quien la escriba a mano.
#
# Las entradas se escriben EXPANDIDAS a proposito: los ratchets de F8 (backend
# t8 y el .test.ts de paridad) parsean este archivo como TEXTO buscando
# `id="..."`, `effect="..."` y `reach=canonical_reach("...")` linea por linea.
# Un helper que armara las entradas dejaria esos literales fuera del archivo y
# volveria los ratchets inertes (dos listas vacias iguales = falso verde).
# --------------------------------------------------------------------------
DEVOPS_ACTION_CATALOG: tuple[DevOpsAction, ...] = (
    # ---------------------------- 16 de LECTURA ----------------------------
    DevOpsAction(
        id="devops.overview.refresh",
        label="Actualizar resumen",
        summary="Vuelve a leer el estado general del panel de DevOps.",
        section_id="resumen",
        nav_path="/devops/resumen",
        effect="read",
        impact="none",
        targets_environment=False,
        health_key="cockpit_enabled",
        flag_key="STACKY_DEVOPS_COCKPIT_ENABLED",
        reach=canonical_reach("read"),
        params=(PRJ,),
        phrases=("resumen de devops", "estado general", "como esta todo"),
    ),
    DevOpsAction(
        id="devops.servers.list",
        label="Listar servidores",
        summary="Muestra los servidores registrados del proyecto.",
        section_id="servidores",
        nav_path="/devops/servidores",
        effect="read",
        impact="none",
        targets_environment=False,
        health_key="servers_enabled",
        flag_key="STACKY_DEVOPS_SERVERS_ENABLED",
        reach=canonical_reach("read"),
        params=(PRJ,),
        phrases=("listar servidores", "que servidores hay", "ver los servidores"),
    ),
    DevOpsAction(
        id="devops.servers.doctor",
        label="Diagnosticar servidores",
        summary="Chequea la conexion con un servidor y reporta que falla.",
        section_id="servidores",
        nav_path="/devops/servidores",
        effect="read",
        impact="none",
        targets_environment=False,
        health_key="connection_doctor_enabled",
        flag_key="STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED",
        reach=canonical_reach("read"),
        params=(
            PRJ,
            ActionParam(name="server_alias", type="string", label="Servidor"),
        ),
        phrases=(
            "estado de los servidores", "chequear conexion",
            "diagnosticar el servidor", "esta caido el servidor",
        ),
    ),
    DevOpsAction(
        id="devops.environments.list",
        label="Listar ambientes",
        summary="Muestra los ambientes declarados del proyecto.",
        section_id="ambientes",
        nav_path="/devops/ambientes",
        effect="read",
        impact="none",
        targets_environment=False,
        health_key="environments_enabled",
        flag_key="STACKY_DEVOPS_ENVIRONMENTS_ENABLED",
        reach=canonical_reach("read"),
        params=(PRJ,),
        phrases=("listar ambientes", "que ambientes hay", "ver los ambientes"),
    ),
    DevOpsAction(
        id="devops.variables.list",
        label="Listar variables",
        summary="Muestra las variables declaradas por ambiente.",
        section_id="variables",
        nav_path="/devops/variables",
        effect="read",
        impact="none",
        targets_environment=False,
        health_key="variables_enabled",
        flag_key="STACKY_DEVOPS_VARIABLES_ENABLED",
        reach=canonical_reach("read"),
        params=(PRJ,),
        phrases=("listar variables", "ver las variables", "que variables hay"),
    ),
    DevOpsAction(
        id="devops.pipelines.inventory",
        label="Inventario de pipelines",
        summary="Lista las pipelines del proyecto con su estado.",
        section_id="inventario-pipelines",
        nav_path="/devops/inventario-pipelines",
        effect="read",
        impact="none",
        targets_environment=False,
        health_key="pipeline_inventory_enabled",
        flag_key="STACKY_PIPELINE_INVENTORY_ENABLED",
        reach=canonical_reach("read"),
        params=(PRJ,),
        phrases=("inventario de pipelines", "que pipelines hay", "listar pipelines"),
    ),
    DevOpsAction(
        id="devops.pipelines.audit",
        label="Auditar pipelines",
        summary="Revisa las pipelines y reporta hallazgos de configuracion.",
        section_id="pipeline-audit",
        nav_path="/devops/pipeline-audit",
        effect="read",
        impact="none",
        targets_environment=False,
        health_key="pipeline_audit_enabled",
        flag_key="STACKY_PIPELINE_AUDIT_ENABLED",
        reach=canonical_reach("read"),
        params=(PRJ,),
        phrases=("auditar pipelines", "revisar las pipelines", "auditoria de pipelines"),
    ),
    DevOpsAction(
        id="devops.pipelines.env_matrix",
        label="Matriz de entornos",
        summary="Compara la configuracion entre los ambientes del proyecto.",
        section_id="matriz-entornos",
        nav_path="/devops/matriz-entornos",
        effect="read",
        impact="none",
        targets_environment=False,
        health_key="env_matrix_enabled",
        flag_key="STACKY_PIPELINE_ENV_MATRIX_ENABLED",
        reach=canonical_reach("read"),
        params=(PRJ,),
        phrases=("matriz de entornos", "comparar entornos", "diferencias entre entornos"),
    ),
    DevOpsAction(
        id="devops.pipeline_edit.preview",
        label="Previsualizar cambio",
        summary="Muestra el diff que aplicaria una edicion de pipeline, sin guardarla.",
        section_id="editar-pipeline",
        nav_path="/devops/editar-pipeline",
        effect="read",
        impact="none",
        targets_environment=False,
        health_key="pipeline_nl_edit_enabled",
        flag_key="STACKY_PIPELINE_NL_EDIT_ENABLED",
        reach=canonical_reach("read"),
        params=(
            PRJ,
            ActionParam(name="instruction", type="string", label="Instruccion",
                        required=True),
        ),
        phrases=(
            "previsualizar el cambio de pipeline", "ver el diff de la pipeline",
            "simular la edicion de pipeline",
        ),
    ),
    DevOpsAction(
        id="devops.deployments.history",
        label="Historial de despliegues",
        summary="Lista los despliegues anteriores con su fecha y resultado.",
        section_id="despliegues",
        nav_path="/devops/despliegues",
        effect="read",
        impact="none",
        targets_environment=False,
        health_key="deployments_enabled",
        flag_key="STACKY_DEPLOYMENTS_ENABLED",
        reach=canonical_reach("read"),
        params=(PRJ,),
        phrases=("historial de despliegues", "ultimos despliegues", "que se desplego"),
    ),
    DevOpsAction(
        id="devops.publications.list",
        label="Listar publicaciones",
        summary="Muestra las publicaciones registradas del proyecto.",
        section_id="publicaciones",
        nav_path="/devops/publicaciones",
        effect="read",
        impact="none",
        targets_environment=False,
        health_key="publications_enabled",
        flag_key="STACKY_DEVOPS_PUBLICATIONS_ENABLED",
        reach=canonical_reach("read"),
        params=(PRJ,),
        phrases=("listar publicaciones", "ver las publicaciones", "que publicaciones hay"),
    ),
    DevOpsAction(
        id="devops.pr.list",
        label="Listar pull requests",
        summary="Muestra los pull requests abiertos del proyecto.",
        section_id="pr-review",
        nav_path="/devops/pr-review",
        effect="read",
        impact="none",
        targets_environment=False,
        health_key="pr_reviewer_enabled",
        flag_key="STACKY_PR_REVIEWER_ENABLED",
        reach=canonical_reach("read"),
        params=(PRJ,),
        phrases=("listar pull requests", "ver los pull requests", "que pull requests hay"),
    ),
    DevOpsAction(
        id="devops.build.status",
        label="Estado de compilacion",
        summary="Muestra como termino la ultima compilacion.",
        section_id="taller-compilacion",
        nav_path="/devops/taller-compilacion",
        effect="read",
        impact="none",
        targets_environment=False,
        health_key="build_workshop_enabled",
        flag_key="STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED",
        reach=canonical_reach("read"),
        params=(PRJ,),
        phrases=("estado de la compilacion", "como viene el build", "ver la compilacion"),
    ),
    DevOpsAction(
        id="devops.handoff.preview",
        label="Previsualizar entrega",
        summary="Arma la vista previa del paquete de entrega, sin generarlo.",
        section_id="paquete-entrega",
        nav_path="/devops/paquete-entrega",
        effect="read",
        impact="none",
        targets_environment=False,
        health_key="handoff_bundle_enabled",
        flag_key="STACKY_PIPELINE_HANDOFF_BUNDLE_ENABLED",
        reach=canonical_reach("read"),
        params=(PRJ,),
        phrases=(
            "previsualizar el paquete de entrega", "ver el paquete de entrega",
            "armar entrega",
        ),
    ),
    # Las 2 de afuera del panel: section_id=None y health_key="" => SIEMPRE visibles.
    DevOpsAction(
        id="devops.logs.tail",
        label="Ver ultimas lineas del log",
        summary="Muestra las ultimas lineas del log del proyecto.",
        section_id=None,
        nav_path="/logs",
        effect="read",
        impact="none",
        targets_environment=False,
        health_key="",
        flag_key="",
        reach=canonical_reach("read"),
        params=(
            PRJ,
            ActionParam(name="lines", type="int", label="Lineas", default="200"),
        ),
        phrases=(
            "ver los logs", "revisar logs", "mostrame el log",
            "ultimas lineas del log",
        ),
    ),
    DevOpsAction(
        id="devops.incidents.list",
        label="Listar incidencias",
        summary="Muestra las incidencias abiertas del proyecto.",
        section_id=None,
        nav_path="/incidencias",
        effect="read",
        impact="none",
        targets_environment=False,
        health_key="",
        flag_key="",
        reach=canonical_reach("read"),
        params=(PRJ,),
        phrases=("listar incidencias", "ver las incidencias", "que incidencias hay"),
    ),
    # ---------------------------- 7 de ESCRITURA ---------------------------
    DevOpsAction(
        id="devops.pipeline.trigger",
        label="Disparar pipeline",
        summary="Lanza una corrida de la pipeline elegida en el entorno elegido.",
        section_id="pipelines",
        nav_path="/devops/pipelines",
        effect="write",
        impact="high",
        targets_environment=True,
        health_key="trigger_enabled",
        flag_key="STACKY_PIPELINE_TRIGGER_ENABLED",
        reach=canonical_reach("write"),
        params=(
            PRJ,
            ENV,
            ActionParam(name="pipeline_id", type="string", label="Pipeline",
                        required=True),
        ),
        phrases=(
            "disparar la pipeline", "correr la pipeline", "ejecutar la pipeline",
            "lanzar la pipeline",
        ),
    ),
    DevOpsAction(
        id="devops.deployment.execute",
        label="Ejecutar despliegue",
        summary="Corre el despliegue elegido en el entorno elegido.",
        section_id="despliegues",
        nav_path="/devops/despliegues",
        effect="write",
        impact="high",
        targets_environment=True,
        health_key="deployments_execute_enabled",
        flag_key="STACKY_DEPLOYMENTS_EXECUTE_ENABLED",
        reach=canonical_reach("write"),
        params=(
            PRJ,
            ENV,
            ActionParam(name="deployment_id", type="string", label="Despliegue",
                        required=True),
        ),
        phrases=("ejecutar el despliegue", "hacer el despliegue", "desplegar ahora"),
    ),
    DevOpsAction(
        id="devops.publication.run",
        label="Correr publicacion",
        summary="Ejecuta la publicacion elegida en el entorno elegido.",
        section_id="publicaciones",
        nav_path="/devops/publicaciones",
        effect="write",
        impact="high",
        targets_environment=True,
        health_key="one_click_publish_enabled",
        flag_key="STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED",
        reach=canonical_reach("write"),
        params=(
            PRJ,
            ENV,
            ActionParam(name="publication_id", type="string", label="Publicacion",
                        required=True),
        ),
        phrases=("correr la publicacion", "ejecutar la publicacion", "publicar ahora"),
    ),
    DevOpsAction(
        id="devops.solution.publish",
        label="Publicar solucion",
        summary="Compila y publica la solucion en el entorno elegido.",
        section_id="publicador-soluciones",
        nav_path="/devops/publicador-soluciones",
        effect="write",
        impact="high",
        targets_environment=True,
        health_key="solution_publisher_enabled",
        flag_key="STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED",
        reach=canonical_reach("write"),
        params=(
            PRJ,
            ENV,
            ActionParam(name="solution_path", type="string", label="Solucion",
                        required=True),
        ),
        phrases=(
            "publicar la solucion", "compilar y publicar la solucion",
            "generar la publicacion de la solucion",
        ),
    ),
    DevOpsAction(
        id="devops.remote_console.run",
        label="Correr comando remoto",
        summary="Ejecuta un comando en el servidor elegido.",
        section_id="remote-console",
        nav_path="/devops/remote-console",
        effect="write",
        impact="high",
        targets_environment=True,
        health_key="remote_console_enabled",
        flag_key="STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED",
        reach=canonical_reach("write"),
        params=(
            PRJ,
            ENV,
            ActionParam(name="server_alias", type="string", label="Servidor",
                        required=True),
            ActionParam(name="command", type="string", label="Comando",
                        required=True),
        ),
        phrases=(
            "correr un comando remoto", "ejecutar en el servidor",
            "comando en la consola remota",
        ),
    ),
    DevOpsAction(
        id="devops.pipeline_edit.commit",
        label="Guardar cambio de pipeline",
        summary="Escribe en el repositorio real el cambio de pipeline ya previsualizado.",
        section_id="editar-pipeline",
        nav_path="/devops/editar-pipeline",
        effect="write",
        impact="high",
        targets_environment=False,
        health_key="pipeline_nl_edit_commit_enabled",
        flag_key="STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED",
        reach=canonical_reach("write"),
        params=(
            PRJ,
            ActionParam(name="branch", type="string", label="Rama", required=True),
        ),
        phrases=(
            "commitear la pipeline editada",
            "guardar el cambio de pipeline en el repositorio",
            "subir el cambio de pipeline",
        ),
    ),
    DevOpsAction(
        id="devops.build.run",
        label="Compilar solucion",
        summary="Compila la solucion indicada y reporta el resultado.",
        section_id="taller-compilacion",
        nav_path="/devops/taller-compilacion",
        effect="write",
        impact="low",
        targets_environment=False,
        # Deuda conocida y declarada [C16]: comparte flag con devops.build.status
        # (read). La flag es preexistente del plan 201; partirla es otro plan.
        health_key="build_workshop_enabled",
        flag_key="STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED",
        reach=canonical_reach("write"),
        params=(
            PRJ,
            ActionParam(name="solution_path", type="string", label="Solucion",
                        required=True),
        ),
        phrases=("compilar la solucion", "correr la compilacion", "buildear el proyecto"),
    ),
)

_INDEX: dict[str, DevOpsAction] = {a.id: a for a in DEVOPS_ACTION_CATALOG}


def get_action(action_id: str) -> DevOpsAction | None:
    """None si no existe. NUNCA lanza."""
    return _INDEX.get((action_id or "").strip())


def visible_actions(health: dict | None) -> list[DevOpsAction]:
    """Acciones alcanzables segun el health del panel. NUNCA lanza.

    Reglas, en este orden:
      1. health_key == ""  => SIEMPRE visible (no depende del panel: son las que
         viven fuera de /devops, como /logs y /incidencias).
      2. resto             => visible solo si el MASTER del panel esta ON
         (health[MASTER_HEALTH_KEY] is True) Y su propio health_key esta ON.

    La regla 2 es el fix de C6: sin ella, con STACKY_DEVOPS_PANEL_ENABLED apagado
    el catalogo seguia ofreciendo ~21 acciones cuyo nav_path (/devops/<seccion>)
    no lleva a ningun lado.
    """
    h = health or {}
    master_on = h.get(MASTER_HEALTH_KEY) is True
    out = []
    for a in DEVOPS_ACTION_CATALOG:
        if not a.health_key:
            out.append(a)
        elif master_on and h.get(a.health_key) is True:
            out.append(a)
    return out


def palette_actions(health: dict | None) -> list[DevOpsAction]:
    """Lo que la paleta global puede OFRECER: reach contiene palette-run o
    palette-nav. Quien decide si ejecuta o navega es el propio reach [C5]."""
    return [a for a in visible_actions(health)
            if "palette-run" in a.reach or "palette-nav" in a.reach]


def assistant_actions(health: dict | None) -> list[DevOpsAction]:
    """Lo que el matcher de F2 tiene permitido proponer. Es el UNICO universo que
    recibe match_intent(): una accion sin 'assistant' en reach jamas se propone."""
    return [a for a in visible_actions(health) if "assistant" in a.reach]


def param_of(action: DevOpsAction, name: str) -> ActionParam | None:
    for p in action.params:
        if p.name == name:
            return p
    return None


def action_to_dict(a: DevOpsAction) -> dict:
    return {
        "id": a.id, "label": a.label, "summary": a.summary,
        "section_id": a.section_id, "nav_path": a.nav_path,
        "effect": a.effect, "impact": a.impact,
        "targets_environment": a.targets_environment,
        "health_key": a.health_key, "flag_key": a.flag_key,
        "reach": list(a.reach),
        "params": [
            {"name": p.name, "type": p.type, "label": p.label,
             "required": p.required, "enum_values": list(p.enum_values),
             "default": p.default}
            for p in a.params
        ],
        "phrases": list(a.phrases),
    }


def catalog_payload(health: dict | None) -> dict:
    acts = visible_actions(health)
    return {
        "ok": True,
        "version": CATALOG_VERSION,
        "count": len(acts),
        "actions": [action_to_dict(a) for a in acts],
    }
