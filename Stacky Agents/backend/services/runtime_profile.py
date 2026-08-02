"""Plan 296 F1 - La ficha COMPLETA de cada runtime.

PURO: sin flask, sin red, sin escritura. Importa `runtime_capabilities` y el
modulo `run_preflight` (para sus dos helpers puros). El gate de "no importa la
capa web" NO se verifica por texto sino por AST en el test: ver C5.

POR QUE NO SE LLAMA A `run_preflight.check`: ese chequeo lee
STACKY_RUN_PREFLIGHT_GATE_ENABLED y, si esta OFF, devuelve PreflightResult(ok=True)
SIN VERIFICAR NADA (run_preflight.py:82-83). Una consulta de disponibilidad
basada en `check()` diria "todo disponible" en cuanto alguien apague esa flag.
Aca se reusan SOLO sus dos helpers puros y se emite veredicto propio.

REGLA DE IMPORT (C16): el modulo importa `run_preflight` COMO MODULO y llama
calificado. Con `from services.run_preflight import _binary_resolvable` el nombre
quedaria ligado en tiempo de import y el monkeypatch del test no tendria efecto:
el test pasaria por la razon equivocada.
"""
from __future__ import annotations

from services import run_preflight
from services.runtime_capabilities import RUNTIMES, capabilities_for

FICHA_VERSION = "1"

#: Las 7 claves que el operador exige, en orden. Cerrado.
FICHA_CAMPOS: tuple[str, ...] = (
    "disponible",          # (1) esta y esta bien configurado?
    "recomendado_para",    # (2) para que tarea conviene?
    "capacidades",         # (3) que va a usar?
    "credenciales",        # (4) que permisos/credenciales pide?
    "ejecucion",           # (5) local o integracion externa?
    "si_falla",            # (6) que pasa si la ejecucion falla?
    "como_cambiar",        # (7) como cambio de runtime antes de ejecutar?
)

#: (2) Para que tarea se recomienda. Declarativo, cerrado sobre RUNTIMES.
RECOMENDADO_PARA: dict[str, tuple[str, ...]] = {
    "claude_code_cli": (
        "Cambios que cruzan varios archivos del repositorio",
        "Trabajo que necesita razonar sobre el código antes de escribirlo",
        "Tareas donde el nivel de esfuerzo importa (es el único con esfuerzo nativo)",
    ),
    "codex_cli": (
        "Cambios acotados a pocos archivos",
        "Tareas repetitivas con un patrón claro",
        "Corridas donde interesa acotar el gasto por presupuesto de turnos",
    ),
    "github_copilot": (
        "Consultas y redacción sin repositorio local",
        "Primer contacto: es el único que no necesita repo git",
        "Tareas cortas dentro del editor",
    ),
}

#: (4) Que necesita para funcionar. NUNCA se muestran valores, solo nombres.
CREDENCIALES: dict[str, tuple[str, ...]] = {
    "claude_code_cli": ("Binario `claude` en el PATH (o ruta absoluta en CLAUDE_CODE_CLI_BIN)",
                        "Sesión iniciada en el CLI de Claude, fuera de Stacky"),
    "codex_cli":       ("Binario `codex` en el PATH (o ruta absoluta en CODEX_CLI_BIN)",
                        "Sesión iniciada en el CLI de Codex, fuera de Stacky"),
    "github_copilot":  ("Suscripción activa de GitHub Copilot",
                        "El puente del editor levantado (LLM_BACKEND en copilot o vscode_bridge)"),
}

#: (5) Donde corre. Derivado de agent_runner.py:319/398 y de _RUNTIMES_REQUIRING_REPO.
EJECUCION: dict[str, str] = {
    "claude_code_cli": "local",
    "codex_cli":       "local",
    "github_copilot":  "integracion_externa",
}

#: (6) Que ocurre si falla. Texto en castellano, sin jerga.
SI_FALLA: dict[str, str] = {
    "claude_code_cli": ("La corrida queda marcada como fallida con el motivo. No se cambia "
                        "de runtime: Stacky te ofrece reintentar o elegir otro vos mismo."),
    "codex_cli":       ("La corrida queda marcada como fallida con el motivo. Si se agotó el "
                        "presupuesto de turnos se dice explícitamente. No se cambia de runtime."),
    "github_copilot":  ("Si el puente del editor no responde, la corrida falla con el motivo. "
                        "No se cambia de runtime."),
}

#: (7) Como cambiar. Unico texto, igual para los 3: es una propiedad del flujo.
COMO_CAMBIAR = ("Antes de ejecutar cualquier acción podés cambiar el runtime desde el "
                "selector del copiloto. El cambio exige una acción tuya: Stacky nunca "
                "lo cambia solo, ni siquiera cuando el runtime elegido falla.")

#: C2 - MEDIDO, no supuesto. Solo UN camino rechaza por falta de archivo de agente:
#: api/agents.py:480 (rechaza con "missing_vscode_agent_filename", :488).
EXIGE_AGENTE_VSCODE: dict[str, bool] = {
    "claude_code_cli": True,   # solo en POST /agents/run
    "codex_cli":       True,   # solo en POST /agents/run
    "github_copilot":  False,
}

#: Alcance textual de la exigencia de arriba. Sin esto la ficha EXAGERA.
EXIGE_AGENTE_VSCODE_ALCANCE = (
    "Sólo al lanzar un agente desde el tablero. En épicas desde brief y en "
    "incidencias, Stacky elige el archivo de agente por vos."
)

#: C2 - los OTROS tres caminos AUTO-RELLENAN en vez de rechazar.
#: api/agents.py:858, :1069, :1261.
AGENTE_VSCODE_POR_DEFECTO: dict[str, str] = {
    "epica_desde_brief":         "BusinessAgent.agent.md",
    "analisis_de_incidencia":    "IncidentAnalyst.agent.md",
    "resolucion_dev_incidencia": "IncidentDevResolver.agent.md",
}

#: [ADICION ARQUITECTO] Cada campo declarativo, atado al literal que lo sostiene.
#: (ruta relativa a backend/, literal que DEBE seguir existiendo, campo que respalda)
FICHA_ANCLAJES: tuple[tuple[str, str, str], ...] = (
    ("api/agents.py",                    "missing_vscode_agent_filename", "exige_agente_vscode"),
    ("api/agents.py",                    "BusinessAgent.agent.md",        "agente_vscode_por_defecto"),
    ("api/agents.py",                    "IncidentAnalyst.agent.md",      "agente_vscode_por_defecto"),
    ("api/agents.py",                    "IncidentDevResolver.agent.md",  "agente_vscode_por_defecto"),
    ("services/run_preflight.py",        "_RUNTIMES_REQUIRING_REPO",      "disponible"),
    ("services/run_preflight.py",        "CLAUDE_CODE_CLI_BIN",           "credenciales"),
    ("services/run_preflight.py",        "CODEX_CLI_BIN",                 "credenciales"),
    ("services/runtime_capabilities.py", "RUNTIMES",                      "runtime"),
    ("agent_runner.py",                  "start_codex_cli_run",           "ejecucion"),
    ("agent_runner.py",                  "start_claude_code_cli_run",     "ejecucion"),
)

_MOTIVO_ASISTENCIA_LLM = (
    "La asistencia por modelo NO depende del runtime que elijas: depende de "
    "LLM_BACKEND, que es otro eje. El copiloto del perfil no la usa: su motor "
    "es determinista y da el mismo resultado con los tres runtimes."
)


def binary_availability(runtime: str) -> dict:
    """Disponibilidad del binario del runtime. NUNCA lanza.

    Cualquier excepcion al resolver deja `binario_resoluble = False`.
    """
    requiere_binario = runtime in run_preflight._RUNTIME_BINS
    requiere_repo_git = runtime in run_preflight._RUNTIMES_REQUIRING_REPO
    binario: str | None = None
    binario_resoluble: bool | None = None

    if requiere_binario:
        binario_resoluble = False
        try:
            env_key = run_preflight._RUNTIME_BINS[runtime]
            binario = str(run_preflight._get_runtime_bin(env_key, runtime))
            binario_resoluble = bool(run_preflight._binary_resolvable(binario))
        except Exception:  # noqa: BLE001 - una ficha nunca puede tumbar la consulta
            binario_resoluble = False

    return {
        "runtime": runtime,
        "requiere_binario": requiere_binario,
        "binario": binario,
        "binario_resoluble": binario_resoluble,
        "requiere_repo_git": requiere_repo_git,
    }


def asistencia_llm() -> dict:
    """Se deriva de config.LLM_BACKEND, NO del runtime elegido. NUNCA lanza."""
    try:
        from config import config as _cfg
        crudo = getattr(_cfg, "LLM_BACKEND", None)
        backend = str(crudo).strip().lower() if crudo else "desconocido"
    except Exception:  # noqa: BLE001
        backend = "desconocido"
    if not backend:
        backend = "desconocido"
    return {
        "modo": "segun_llm_backend",
        "llm_backend": backend,
        "motivo": _MOTIVO_ASISTENCIA_LLM,
    }


def _capacidades(runtime: str) -> dict:
    caps = dict(capabilities_for(runtime))
    caps["exige_agente_vscode"] = EXIGE_AGENTE_VSCODE.get(runtime, False)
    caps["exige_agente_vscode_alcance"] = EXIGE_AGENTE_VSCODE_ALCANCE
    caps["agente_vscode_por_defecto"] = dict(AGENTE_VSCODE_POR_DEFECTO)
    caps["asistencia_llm"] = asistencia_llm()
    return caps


def runtime_profile(runtime: str, *, project_name: str | None = None) -> dict:
    """Ficha de 7 campos de un runtime. NUNCA lanza, nunca devuelve None.

    `project_name` viaja para que el llamador pueda declarar el contexto de la
    consulta; la ficha de hoy es identica para todo proyecto (el motor es
    determinista, P3). Se acepta para no romper el contrato cuando alguna
    fuente pase a depender del proyecto.
    """
    conocido = runtime in RUNTIMES
    detalle = binary_availability(runtime)

    if not conocido:
        disponible = False
        motivo = "Runtime desconocido."
    elif not detalle["requiere_binario"]:
        disponible = True
        motivo = ""
    else:
        disponible = bool(detalle["binario_resoluble"])
        motivo = "" if disponible else (
            f"No encontré el programa '{detalle['binario']}'. "
            f"Instalalo o indicá su ruta completa."
        )

    return {
        "runtime": runtime,
        "conocido": conocido,
        "version_ficha": FICHA_VERSION,
        "proyecto": project_name or "",
        # (1)
        "disponible": disponible,
        "disponibilidad_detalle": detalle,
        "disponibilidad_motivo": motivo,
        # (2)
        "recomendado_para": list(RECOMENDADO_PARA.get(runtime, ())),
        # (3)
        "capacidades": _capacidades(runtime),
        # (4)
        "credenciales": list(CREDENCIALES.get(runtime, ())),
        # (5)
        "ejecucion": EJECUCION.get(runtime, "desconocida"),
        # (6)
        "si_falla": SI_FALLA.get(
            runtime,
            "No se puede anticipar qué ocurre: este runtime no está declarado en Stacky.",
        ),
        # (7)
        "como_cambiar": COMO_CAMBIAR,
    }


def all_runtime_profiles(*, project_name: str | None = None) -> list[dict]:
    """Las fichas de los 3 runtimes conocidos, en el orden de RUNTIMES."""
    return [runtime_profile(r, project_name=project_name) for r in RUNTIMES]


def recomendar_runtime(fichas: list[dict]) -> dict:
    """Sugerencia determinista y explicada. NUNCA decide: el caller no la aplica."""
    disponibles = [f for f in (fichas or []) if f.get("disponible") is True]
    if len(disponibles) == 1:
        return {
            "runtime": disponibles[0].get("runtime"),
            "motivo": "Es el único disponible ahora mismo.",
        }
    if len(disponibles) > 1:
        por_id = {f.get("runtime") for f in disponibles}
        for r in RUNTIMES:
            if r in por_id:
                return {
                    "runtime": r,
                    "motivo": (
                        "Está disponible y es el que más capacidades declara para "
                        "trabajo sobre el repositorio."
                    ),
                }
        primero = disponibles[0]
        return {
            "runtime": primero.get("runtime"),
            "motivo": "Está disponible y es el primero de la lista consultada.",
        }
    return {
        "runtime": None,
        "motivo": "Ninguno está disponible: revisá la ficha de cada uno.",
    }
