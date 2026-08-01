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
    "copiloto-pipelines",   # Plan 279 — seccion 18: el copiloto de pipelines
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
# Params reusados por las 23 entradas. `project` es el PRIMER param de todas
# (test_todas_declaran_project), pero NO es required en todas: ver abajo.
#
# --- CORRECCION F7: los params se declaran POR ACCION, no por plantilla ------
#
# Hasta la v4 este bloque exportaba tambien `ENV`, un param `environment` de tipo
# enum con `enum_values=("dev","qa","uat","prod")` y `required=True`, y se lo
# pegaba como segundo param a 5 de las 7 escrituras copiando el contrato de la
# accion mas exigente. MEDIDO al construir F7, y es la causa raiz de que la fase
# quedara bloqueada:
#
#   1. Esa tupla de 4 valores NO EXISTE EN NINGUN OTRO LUGAR DEL SISTEMA. Un
#      barrido de `backend/` + `frontend/src/` encuentra el literal
#      "dev","qa","uat","prod" en exactamente 2 archivos: este, y la copia
#      espejada en FALLBACK_META. Ningun endpoint lo recibe, ninguna pantalla lo
#      ofrece, ninguna config lo define. Era vocabulario inventado.
#   2. NINGUN endpoint real de las 5 acciones consume un `environment`. Se
#      verifico binding por binding en frontend/src/services/devopsActionBindings.ts:
#        - devops.solution.publish   -> DevOpsSolutionPublisher.run(solution_path)
#        - devops.remote_console.run -> DevOpsRemoteConsole.exec(alias, command, conv?)
#        - devops.pipeline.trigger   -> CIPipeline.trigger(project, ref, ...)
#        - devops.publication.run    -> delega en la pantalla (no llama endpoint)
#        - devops.deployment.execute -> DevOpsDeployments.execute(app_id, targets, ...)
#          El unico que USABA el valor lo pasaba como la lista de DESTINOS, y los
#          destinos reales son "__local__" o un alias de servidor
#          (frontend/src/components/devops/deploymentsModel.ts:90-96), nunca uno
#          de los 4 valores del enum. La llamada no podia funcionar.
#   3. `runDevOpsAction` corta con ok:false ANTES de confirmar si falta un param
#      required. Un enum required que nadie puede proveer = boton muerto con
#      "Faltan datos obligatorios".
#
# La guarda de requeridos NO se toco: sigue bloqueando todo param que el endpoint
# de verdad necesita. Lo que se corrigio es la DECLARACION, que pedia datos que la
# llamada nunca recibe. `project` queda required solo donde el endpoint lo recibe.
#
# Si alguna vez nace una accion que SI actua sobre un entorno concreto, el shape
# obligatorio de su param esta especificado por
# tests/test_devops_action_ratchet.py::test_targets_environment_exige_param_environment
# (name="environment", type="enum", required=True, enum_values no vacio) — y ese
# enum tiene que salir de una fuente real, no de una tupla escrita aca.
# --------------------------------------------------------------------------
PRJ = ActionParam(name="project", type="string", label="Proyecto", required=True)

# `project` para las acciones cuyo endpoint real NO lo recibe. Se sigue
# DECLARANDO (el asistente lo usa para el deep-link y para el encabezado de la
# tarjeta) pero no bloquea la ejecucion, porque no hay nada que bloquear.
PRJ_OPT = ActionParam(name="project", type="string", label="Proyecto", required=False)


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
    # ---------------------------- 21 de LECTURA ----------------------------
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
    # ── Plan 279 — Copiloto de pipelines: el ciclo de creacion, 5 de LECTURA ──
    # Las 5 envuelven rutas HTTP que YA existen; ningun endpoint backend nuevo.
    # `label` y `phrases` son LITERALES del plan 279 F3 [C5]: el gate de colision
    # read/write (test_devops_action_ratchet.py:111) evalua (*phrases, label), y
    # se verifico con _content_tokens+normalize_text reales: 0 choques.
    DevOpsAction(
        id="devops.pipeline_new.draft",
        label="Armar borrador de pipeline",
        summary="Genera un borrador de pipeline a partir de lo que necesitas. No escribe nada.",
        section_id="copiloto-pipelines",
        nav_path="/devops/copiloto-pipelines",
        effect="read",
        impact="none",
        targets_environment=False,
        health_key="pipeline_copilot_enabled",
        flag_key="STACKY_PIPELINE_COPILOT_ENABLED",
        reach=canonical_reach("read"),
        params=(
            PRJ,
            ActionParam(name="need", type="string", label="Que necesitas",
                        required=True),
        ),
        phrases=(
            "borrador de pipeline nueva",
            "armar el borrador de una pipeline",
            "disenar una pipeline nueva",
        ),
    ),
    DevOpsAction(
        id="devops.pipeline_new.lint",
        label="Revisar borrador de pipeline",
        summary="Corre el lint sobre el borrador y devuelve los hallazgos con su linea.",
        section_id="copiloto-pipelines",
        nav_path="/devops/copiloto-pipelines",
        effect="read",
        impact="none",
        targets_environment=False,
        health_key="pipeline_copilot_enabled",
        flag_key="STACKY_PIPELINE_COPILOT_ENABLED",
        reach=canonical_reach("read"),
        params=(
            PRJ,
            ActionParam(name="draft_ref", type="string", label="Borrador",
                        required=True),
        ),
        phrases=(
            "revisar el borrador de pipeline",
            "validar el yaml del borrador",
            "que errores tiene el borrador",
        ),
    ),
    DevOpsAction(
        id="devops.pipeline_new.explain",
        label="Explicar borrador de pipeline",
        summary="Describe en castellano que etapas y pasos va a correr el borrador.",
        section_id="copiloto-pipelines",
        nav_path="/devops/copiloto-pipelines",
        effect="read",
        impact="none",
        targets_environment=False,
        health_key="pipeline_copilot_enabled",
        flag_key="STACKY_PIPELINE_COPILOT_ENABLED",
        reach=canonical_reach("read"),
        params=(
            PRJ,
            ActionParam(name="draft_ref", type="string", label="Borrador",
                        required=True),
        ),
        phrases=(
            "explicar el borrador de pipeline",
            "que va a hacer el borrador",
            "explicame los pasos del borrador",
        ),
    ),
    DevOpsAction(
        id="devops.pipeline_new.preflight",
        label="Chequeos previos del borrador",
        summary="Semaforo estatico del borrador: placeholders y variables sin definir.",
        section_id="copiloto-pipelines",
        nav_path="/devops/copiloto-pipelines",
        effect="read",
        impact="none",
        targets_environment=False,
        health_key="pipeline_copilot_enabled",
        flag_key="STACKY_PIPELINE_COPILOT_ENABLED",
        reach=canonical_reach("read"),
        params=(
            PRJ,
            ActionParam(name="draft_ref", type="string", label="Borrador",
                        required=True),
        ),
        phrases=(
            "preflight del borrador de pipeline",
            "semaforo del borrador",
            "chequeos previos del borrador",
        ),
    ),
    DevOpsAction(
        id="devops.pipeline_new.secrets",
        label="Variables que faltan para el borrador",
        summary="Lista por NOMBRE las variables y secretos que el borrador necesita y el proyecto no define.",
        section_id="copiloto-pipelines",
        nav_path="/devops/copiloto-pipelines",
        effect="read",
        impact="none",
        targets_environment=False,
        health_key="pipeline_copilot_enabled",
        flag_key="STACKY_PIPELINE_COPILOT_ENABLED",
        reach=canonical_reach("read"),
        params=(
            PRJ,
            ActionParam(name="draft_ref", type="string", label="Borrador",
                        required=True),
        ),
        phrases=(
            "que variables le faltan al borrador",
            "secretos que necesita el borrador",
            "credenciales que faltan para la pipeline",
        ),
    ),
    # ---------------------------- 8 de ESCRITURA ---------------------------
    DevOpsAction(
        id="devops.pipeline.trigger",
        label="Disparar pipeline",
        # F7: decia "en el entorno elegido". El endpoint identifica la corrida por
        # su REF (rama): CIPipeline.trigger(project, ref, ...). No hay entorno.
        summary="Lanza una corrida de la pipeline en la rama elegida.",
        section_id="pipelines",
        nav_path="/devops/pipelines",
        effect="write",
        impact="high",
        targets_environment=False,
        health_key="trigger_enabled",
        flag_key="STACKY_PIPELINE_TRIGGER_ENABLED",
        reach=canonical_reach("write"),
        # `project` SI lo recibe el endpoint => queda required.
        params=(
            PRJ,
            ActionParam(name="pipeline_id", type="string", label="Rama o pipeline",
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
        # F7: decia "en el entorno elegido". Los destinos reales son claves de
        # tarjeta: "__local__" o el alias de un servidor registrado.
        summary="Corre el despliegue elegido en los destinos elegidos.",
        section_id="despliegues",
        nav_path="/devops/despliegues",
        effect="write",
        impact="high",
        targets_environment=False,
        health_key="deployments_execute_enabled",
        flag_key="STACKY_DEPLOYMENTS_EXECUTE_ENABLED",
        reach=canonical_reach("write"),
        # `project`: DevOpsDeployments.execute(app_id, targets, ...) no lo recibe.
        # `targets` reemplaza al `environment` inventado: es el dato que el
        # endpoint SI consume, y su vocabulario es el real (claves de destino).
        params=(
            PRJ_OPT,
            ActionParam(name="deployment_id", type="string", label="Aplicacion",
                        required=True),
            ActionParam(name="targets", type="string", label="Destinos",
                        required=True),
        ),
        phrases=("ejecutar el despliegue", "hacer el despliegue", "desplegar ahora"),
    ),
    DevOpsAction(
        id="devops.publication.run",
        label="Correr publicacion",
        # F7: decia "en el entorno elegido". La publicacion es una cadena de pasos
        # sobre un preset del perfil del proyecto; no hay entorno.
        summary="Ejecuta la publicacion elegida del proyecto activo.",
        section_id="publicaciones",
        nav_path="/devops/publicaciones",
        effect="write",
        impact="high",
        targets_environment=False,
        health_key="one_click_publish_enabled",
        flag_key="STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED",
        reach=canonical_reach("write"),
        # `project` SI se consume: la cadena arranca con
        # DevOps.materializePublication(project, presetName). `publication_id` es
        # el nombre del preset.
        params=(
            PRJ,
            ActionParam(name="publication_id", type="string", label="Publicacion",
                        required=True),
        ),
        phrases=("correr la publicacion", "ejecutar la publicacion", "publicar ahora"),
    ),
    DevOpsAction(
        id="devops.solution.publish",
        label="Publicar solucion",
        # F7: decia "en el entorno elegido". DevOpsSolutionPublisher.run(slug) no
        # recibe entorno; la salida va a una carpeta propia de Stacky.
        summary="Compila y publica la solucion elegida.",
        section_id="publicador-soluciones",
        nav_path="/devops/publicador-soluciones",
        effect="write",
        impact="high",
        targets_environment=False,
        health_key="solution_publisher_enabled",
        flag_key="STACKY_DEVOPS_SOLUTION_PUBLISHER_ENABLED",
        reach=canonical_reach("write"),
        # `project`: el endpoint no lo recibe (identifica por slug de solucion).
        params=(
            PRJ_OPT,
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
        # F7: actua sobre un SERVIDOR, no sobre un entorno. El summary ya lo decia
        # bien; era `targets_environment` + el param los que mentian.
        targets_environment=False,
        health_key="remote_console_enabled",
        flag_key="STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED",
        reach=canonical_reach("write"),
        # `project`: DevOpsRemoteConsole.exec(alias, command, conv?) no lo recibe.
        params=(
            PRJ_OPT,
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
        # `project`: DevOpsBuildWorkshop.compile(slugs, unified) no lo recibe, y
        # el Taller no tiene un proyecto en alcance (su seccion recibe solo `ctx`).
        params=(
            PRJ_OPT,
            ActionParam(name="solution_path", type="string", label="Solucion",
                        required=True),
        ),
        phrases=("compilar la solucion", "correr la compilacion", "buildear el proyecto"),
    ),
    # ── Plan 279 — Copiloto de pipelines: la UNICA escritura del plan ─────────
    # Escribe el archivo de pipeline en el repositorio REAL del operador, asi que
    # su flag nace OFF (excepcion dura (B)). El binding llama a
    # POST /api/pipeline-generator/commit, que ya exige confirm=True (HITL).
    DevOpsAction(
        id="devops.pipeline_new.commit",
        label="Crear la pipeline en el repositorio",
        summary="Escribe el archivo de pipeline en la rama elegida del repositorio real. Pide confirmacion.",
        section_id="copiloto-pipelines",
        nav_path="/devops/copiloto-pipelines",
        effect="write",
        impact="high",
        targets_environment=False,
        health_key="pipeline_copilot_commit_enabled",
        flag_key="STACKY_PIPELINE_COPILOT_COMMIT_ENABLED",
        reach=canonical_reach("write"),
        params=(
            PRJ,
            ActionParam(name="draft_ref", type="string", label="Borrador",
                        required=True),
            ActionParam(name="branch", type="string", label="Rama",
                        required=True),
        ),
        phrases=(
            "crear la pipeline nueva en el repositorio",
            "publicar el borrador de pipeline",
            "guardar la pipeline nueva en el repo",
        ),
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
