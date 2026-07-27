"""services/pipeline_capability_frontier.py — Plan 252 F0/F1. Frontera de capacidades.

Declara, COMO DATO, que acciones del dominio de pipelines puede ejecutar Stacky por si
mismo y cuales no, con el motivo. PURO en F0 (cero I/O, cero red, cero config): las
sondas de estado real viven en F1 y se inyectan.

Este modulo describe la frontera; jamas la cruza: no importa ningun modulo de ejecucion
remota ni de red. La lista negra vive en UN solo lugar — _MODULOS_PROHIBIDOS en
tests/test_plan252_capability_frontier.py — y se verifica por AST, no por texto.

FALLA CERRADO, siempre: una sonda que no se pudo evaluar NO promueve nada. UNKNOWN se
trata como CANNOT_NOW, o sea suma un paso manual al README en vez de omitirlo.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

CATALOG_VERSION = "252.1"

# Veredictos declarados (los del catalogo)
CAN = "CAN"
DEPENDS = "DEPENDS"
CANNOT = "CANNOT"
# Veredictos efectivos adicionales (los que salen de resolver DEPENDS contra el entorno)
CANNOT_NOW = "CANNOT_NOW"   # podria, pero hoy le falta la sonda
UNKNOWN = "UNKNOWN"         # no se pudo evaluar la sonda -> se trata como CANNOT_NOW

_DECLARED_VERDICTS = frozenset({CAN, DEPENDS, CANNOT})
_EFFECTIVE_VERDICTS = frozenset({CAN, CANNOT, CANNOT_NOW, UNKNOWN})

PROBE_IDS: tuple = ("ado_pat", "gitlab_token", "repo_writer")


@dataclass(frozen=True)
class CapabilityAction:
    id: str
    label: str
    verdict: str               # in _DECLARED_VERDICTS
    reason: str                # OBLIGATORIO no vacio
    probes: tuple = ()         # OR entre ellas; solo si DEPENDS
    manual_instruction: str = ""
    needs_deploy: bool = False
    evidence: str = ""         # "modulo.simbolo" del ejecutor REAL.
                               # OBLIGATORIO si verdict in (CAN, DEPENDS); "" si CANNOT.


@dataclass(frozen=True)
class ResolvedAction:
    action: CapabilityAction
    effective: str
    probe_detail: str


# ── El catalogo: 14 filas, ni una mas ni una menos ───────────────────────────
#
# REGLA DURA (§5.1): una fila solo puede declararse CAN o DEPENDS si nombra un ejecutor
# REAL e importable. Las filas 8, 10 y 11 bajaron de DEPENDS a CANNOT respecto de la
# tabla del §5 porque en este arbol NO existe ningun simbolo que cree un variable group,
# un environment con approvals ni un agent pool (verificado con grep). Inventar un
# simbolo para que el test pase seria exactamente el fraude que `evidence` existe para
# impedir: el README le prometeria al operador trabajo ya hecho que no esta hecho.

ACTION_CATALOG: tuple = (
    CapabilityAction(
        id="generate_yaml",
        label="Generar el YAML del pipeline",
        verdict=CAN,
        reason="El renderer es determinista y local: no necesita credenciales ni red.",
        evidence="services.pipeline_renderers.to_ado_yaml",
    ),
    CapabilityAction(
        id="generate_helper_scripts",
        label="Generar los scripts auxiliares que el pipeline invoca",
        verdict=CAN,
        reason="Son texto; se emiten junto al YAML dentro del mismo paquete.",
        evidence="services.pipeline_handoff_bundle.build_files",
    ),
    CapabilityAction(
        id="commit_yaml_to_repo",
        label="Escribir el YAML en el repo (rama + commit)",
        verdict=DEPENDS,
        reason="Stacky sabe commitear, pero necesita un proveedor que implemente el "
               "puerto de escritura del repo. Siempre con confirmación humana.",
        probes=("repo_writer",),
        manual_instruction="Copiá el .yml del paquete al repo y commiteálo a una rama.",
        evidence="services.repo_writer.get_repo_writer",
    ),
    CapabilityAction(
        id="open_pull_request",
        label="Abrir el PR/MR con el YAML",
        verdict=DEPENDS,
        reason="Requiere una credencial del proveedor con permiso de escritura de PR.",
        probes=("ado_pat", "gitlab_token"),
        manual_instruction="Abrí el PR a mano desde la web del proveedor.",
        evidence="services.tracker_provider.get_tracker_provider",
    ),
    CapabilityAction(
        id="register_pipeline_definition",
        label="Dar de alta la definición de pipeline en el proveedor",
        verdict=DEPENDS,
        reason="Requiere una credencial con alcance de Build y confirmación humana.",
        probes=("ado_pat",),
        manual_instruction="Pipelines → New pipeline → Existing Azure Pipelines YAML "
                           "file, y elegí la ruta del .yml.",
        evidence="services.ado_pipeline_definitions.ensure_yaml_definition",
    ),
    CapabilityAction(
        id="set_pipeline_variables",
        label="Cargar las variables NO secretas de la pipeline",
        verdict=DEPENDS,
        reason="Requiere credencial y permiso sobre las variables del proyecto.",
        probes=("ado_pat", "gitlab_token"),
        manual_instruction="Cargá una por una las variables listadas en el README.",
        evidence="services.ci_variables.get_variables_provider",
    ),
    CapabilityAction(
        id="set_pipeline_secrets",
        label="Cargar los VALORES secretos de las variables",
        verdict=CANNOT,
        reason="Por diseño: Stacky nunca transporta valores secretos. El paquete nombra "
               "qué secretos hacen falta, jamás cuánto valen.",
        manual_instruction="Cargá cada secreto marcado en el README, en la UI del "
                           "proveedor, con la casilla de secreto tildada.",
    ),
    CapabilityAction(
        id="create_variable_group",
        label="Crear un grupo de variables / Library",
        verdict=CANNOT,
        reason="Stacky todavía no tiene un ejecutor para esto: no hay ningún símbolo en "
               "este build que cree un variable group.",
        manual_instruction="Pipelines → Library → + Variable group.",
    ),
    CapabilityAction(
        id="create_service_connection",
        label="Crear un service connection",
        verdict=CANNOT,
        reason="Exige el consentimiento de una identidad (service principal / OAuth) y "
               "rol de administrador del proyecto: no es una llamada de API que una "
               "credencial de build pueda hacer sin más.",
        manual_instruction="Project settings → Service connections → New.",
    ),
    CapabilityAction(
        id="create_environment_and_approvals",
        label="Crear el entorno y su compuerta de aprobación",
        verdict=CANNOT,
        reason="Stacky todavía no tiene un ejecutor para esto; y además el approval "
               "define QUIÉN aprueba, que es una decisión humana.",
        manual_instruction="Pipelines → Environments → New environment, y agregá los "
                           "aprobadores.",
    ),
    CapabilityAction(
        id="create_agent_pool",
        label="Crear el pool de agentes",
        verdict=CANNOT,
        reason="Stacky todavía no tiene un ejecutor para esto, y crear un pool exige rol "
               "de administrador a nivel organización.",
        manual_instruction="Project settings → Agent pools → Add pool.",
    ),
    CapabilityAction(
        id="install_selfhosted_agent",
        label="Instalar y registrar el agente self-hosted en el servidor destino",
        verdict=CANNOT,
        reason="Stacky no ejecuta nada en el servidor destino. El agente se instala "
               "corriendo un instalador EN esa máquina, con una cuenta de esa máquina.",
        manual_instruction="Descargá el agente, corré config.cmd, registralo en el pool "
                           "y dejalo como servicio.",
        needs_deploy=True,
    ),
    CapabilityAction(
        id="install_server_prerequisites",
        label="Instalar IIS / roles de Windows / herramientas de compilación en el servidor",
        verdict=CANNOT,
        reason="Misma razón que el agente: es administración del sistema operativo del "
               "servidor destino, y Stacky no cruza esa frontera.",
        manual_instruction="Ejecutá los pasos del README como administrador en el servidor.",
        needs_deploy=True,
    ),
    CapabilityAction(
        id="run_pipeline_first_time",
        label="Disparar la primera corrida",
        verdict=DEPENDS,
        reason="Requiere la definición ya registrada y un agente en línea; y la primera "
               "corrida la autoriza el operador.",
        probes=("ado_pat",),
        manual_instruction="Run pipeline desde la web, con los parámetros que indica el "
                           "README.",
        evidence="services.ci_provider.get_ci_provider",
    ),
)


def get_action(action_id: str) -> Optional[CapabilityAction]:
    for a in ACTION_CATALOG:
        if a.id == action_id:
            return a
    return None


def resolve_frontier(probes: dict, *, pipeline_deploys: bool = False) -> list:
    """PURA. `probes` = dict[probe_id, bool|None]; None/ausente = NO evaluable.

    Falla cerrado en los tres bordes:
      - `probes` vacio -> toda DEPENDS cae en UNKNOWN, jamas en CAN;
      - una CANNOT declarada NO la promueve ninguna sonda;
      - UNKNOWN se cuenta como trabajo manual, no como resuelto.
    """
    probes = dict(probes or {})
    salida: list = []
    for accion in ACTION_CATALOG:
        if accion.needs_deploy and not pipeline_deploys:
            continue
        if accion.verdict == CAN:
            salida.append(ResolvedAction(accion, CAN, ""))
            continue
        if accion.verdict == CANNOT:
            salida.append(ResolvedAction(accion, CANNOT, ""))
            continue
        # DEPENDS
        valores = {p: probes.get(p) for p in accion.probes}
        disponible = next((p for p, v in valores.items() if v is True), None)
        if disponible is not None:
            salida.append(ResolvedAction(accion, CAN, "%s disponible" % disponible))
            continue
        no_evaluables = [p for p, v in valores.items() if v is None]
        if no_evaluables:
            salida.append(ResolvedAction(
                accion, UNKNOWN, "no evaluable: %s" % ", ".join(sorted(no_evaluables))))
            continue
        salida.append(ResolvedAction(
            accion, CANNOT_NOW, "falta: %s" % ", ".join(accion.probes)))
    return salida


def manual_actions(resolved: list) -> list:
    return [r for r in resolved if r.effective in (CANNOT, CANNOT_NOW, UNKNOWN)]


def automatic_actions(resolved: list) -> list:
    return [r for r in resolved if r.effective == CAN]


# ── F1 — sondas del estado real (la UNICA capa con I/O) ─────────────────────

def _probe_ado_pat() -> Optional[bool]:
    """True/False si se pudo evaluar; None si no se pudo. Una sonda NUNCA tumba nada."""
    try:
        from services.ado_client import ado_pat_present
        return bool(ado_pat_present())
    except Exception:  # noqa: BLE001
        return None


def _probe_gitlab_token() -> Optional[bool]:
    """Espeja la precedencia de gitlab_client (variable de entorno > archivo).
    No existe un `gitlab_token_present()` al que delegar."""
    try:
        import os

        from runtime_paths import backend_root
        if (os.getenv("GITLAB_TOKEN") or "").strip():
            return True
        return (backend_root() / "auth" / "gitlab_auth.json").is_file()
    except Exception:  # noqa: BLE001
        return None


def _probe_repo_writer() -> Optional[bool]:
    try:
        from services.repo_writer import get_repo_writer
        return get_repo_writer() is not None
    except Exception:  # noqa: BLE001
        return None


_PROBE_FUNCS = {
    "ado_pat": _probe_ado_pat,
    "gitlab_token": _probe_gitlab_token,
    "repo_writer": _probe_repo_writer,
}


def probe_environment() -> dict:
    """Ejecuta las 3 sondas. NUNCA lanza. dict[probe_id, bool|None]."""
    return {pid: fn() for pid, fn in _PROBE_FUNCS.items()}


def evaluate_frontier(*, pipeline_deploys: bool = False) -> list:
    """probe_environment() + resolve_frontier(). La UNICA funcion del modulo con I/O."""
    return resolve_frontier(probe_environment(), pipeline_deploys=pipeline_deploys)
