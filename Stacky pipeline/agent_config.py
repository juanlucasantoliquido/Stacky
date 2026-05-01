"""
agent_config — Configuración por-agente, por-proyecto.

Permite al usuario personalizar el comportamiento de cada agente (PM, DEV,
Tester, Doc) sin tocar código. La config vive en:

    projects/<NAME>/agents/<agent>.config.json

Cuando el prompt_builder arma el prompt del agente, llama a
`build_prompt_injection(agent, project)` y recibe un bloque de texto que se
apendea al prompt base — con instrucciones extra, nivel de strictness, tests
permitidos/prohibidos, etc.

Caso de uso principal: QA Tester demasiado estricto que rechaza tickets por
cosas cosméticas. El usuario baja strictness a "permissive" y el tester solo
rechaza por bloqueantes reales.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional


# ── Valores por defecto por agente ────────────────────────────────────────────
# Cada agente tiene un perfil default que se considera el "comportamiento
# normal". El usuario solo sobreescribe lo que quiere cambiar.

@dataclass
class AgentConfig:
    """Config genérica de un agente."""
    enabled:            bool   = True
    strictness:         str    = "normal"      # strict | normal | permissive
    extra_instructions: str    = ""            # texto libre del usuario
    notes:              str    = ""            # notas internas, no inyectado
    # Específico QA (ignorados para otros agentes)
    allowed_tests:      list[str] = field(default_factory=lambda: ["*"])
    forbidden_tests:    list[str] = field(default_factory=list)
    blocker_criteria:   list[str] = field(default_factory=lambda: [
        "compile_error", "runtime_crash", "data_corruption",
        "security_breach",
    ])
    advisory_criteria:  list[str] = field(default_factory=lambda: [
        "style_issue", "typo", "best_practice", "minor_ui_glitch",
    ])
    auto_approve_with_observations: bool = True
    # Específico PM (ignorados para otros)
    skip_queries:       bool = False
    require_analysis:   bool = True
    # Específico DEV
    require_tests:      bool = False
    require_commit_msg: bool = True


# Agentes soportados — cualquier otro valor se rechaza en el endpoint
KNOWN_AGENTS = ("pm", "dev", "tester", "doc")

# Strictness válidos
VALID_STRICTNESS = ("strict", "normal", "permissive")


def _config_path(project_root: str, agent: str) -> str:
    """Ruta al archivo de config para un agente de un proyecto."""
    return os.path.join(project_root, "agents", f"{agent}.config.json")


def _project_root_from_workspace(workspace_root: str, project_name: str) -> str:
    """projects/<NAME> dentro del workspace."""
    return os.path.join(workspace_root, "projects", project_name)


def load_agent_config(
    project_root_or_workspace: str,
    agent: str,
    project_name: Optional[str] = None,
) -> AgentConfig:
    """
    Carga la config del agente. Si no existe, devuelve el default.

    Args:
        project_root_or_workspace: puede ser `projects/<NAME>` directamente
                                    o el workspace raíz (en cuyo caso
                                    project_name es obligatorio).
        agent: pm | dev | tester | doc
        project_name: necesario si pasaste el workspace raíz.
    """
    if agent not in KNOWN_AGENTS:
        raise ValueError(f"Agente desconocido: {agent}")

    if project_name:
        project_root = _project_root_from_workspace(project_root_or_workspace,
                                                     project_name)
    else:
        project_root = project_root_or_workspace

    path = _config_path(project_root, agent)
    if not os.path.exists(path):
        return AgentConfig()

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return AgentConfig()

    # Solo copiamos campos conocidos — evita basura
    base = AgentConfig()
    known = set(asdict(base).keys())
    clean = {k: v for k, v in data.items() if k in known}
    return AgentConfig(**{**asdict(base), **clean})


def save_agent_config(
    project_root_or_workspace: str,
    agent: str,
    config: AgentConfig,
    project_name: Optional[str] = None,
) -> str:
    """Persiste la config. Crea la carpeta agents/ si no existe."""
    if agent not in KNOWN_AGENTS:
        raise ValueError(f"Agente desconocido: {agent}")
    if config.strictness not in VALID_STRICTNESS:
        raise ValueError(f"Strictness inválido: {config.strictness}")

    if project_name:
        project_root = _project_root_from_workspace(project_root_or_workspace,
                                                     project_name)
    else:
        project_root = project_root_or_workspace

    os.makedirs(os.path.join(project_root, "agents"), exist_ok=True)
    path = _config_path(project_root, agent)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(config), f, indent=2, ensure_ascii=False)
    return path


# ── Construcción del bloque de prompt injection ───────────────────────────────
# El texto resultante se apendea al final del prompt base del agente.

def build_prompt_injection(agent: str, config: AgentConfig) -> str:
    """
    Traduce la config del agente a instrucciones en lenguaje natural para
    apendear al prompt. Devuelve "" si la config es default (no hay nada que
    inyectar).
    """
    if not config.enabled:
        # Agente deshabilitado — el llamador debería decidir qué hacer
        return (
            "\n\n## ⚠️ AGENTE DESHABILITADO POR CONFIG\n"
            "Este agente fue deshabilitado en la configuración del proyecto. "
            "Si llegaste acá es porque algo invocó el flow de todas formas — "
            "pasá por alto el trabajo y salí.\n"
        )

    lines: list[str] = []
    default = AgentConfig()

    # Strictness global — aplica sobre todo a QA, pero ayuda a PM/DEV también
    if config.strictness != default.strictness:
        if agent == "tester":
            lines.append(_tester_strictness_block(config.strictness))
        else:
            lines.append(_generic_strictness_block(config.strictness))

    # Instrucciones libres del usuario (si las hay)
    if config.extra_instructions and config.extra_instructions.strip():
        lines.append(
            "## 📌 Instrucciones adicionales del usuario\n"
            f"{config.extra_instructions.strip()}\n"
            "\nEstas instrucciones son configuración del proyecto. "
            "Acatalas salvo que entren en conflicto con las reglas básicas "
            "de tu rol (seguridad, corrección, integridad de datos)."
        )

    # Específico QA: tests permitidos/prohibidos, criterios de blocker/advisory
    if agent == "tester":
        qa_lines = _tester_qa_block(config)
        if qa_lines:
            lines.append(qa_lines)

    # Específico PM
    if agent == "pm":
        if config.skip_queries != default.skip_queries:
            lines.append(
                "## Alcance PM\n"
                + ("NO generes QUERIES_ANALISIS.sql — el usuario ya tiene "
                   "las queries necesarias." if config.skip_queries
                   else "Generá QUERIES_ANALISIS.sql de forma normal.")
            )
        if config.require_analysis != default.require_analysis:
            lines.append(
                "## Alcance análisis\n"
                + ("Podés saltar análisis técnico profundo si el ticket es "
                   "trivial." if not config.require_analysis
                   else "Siempre hacé análisis técnico completo.")
            )

    # Específico DEV
    if agent == "dev":
        if config.require_tests != default.require_tests:
            lines.append(
                "## Tests\n"
                + ("Incluí tests unitarios para cualquier código nuevo."
                   if config.require_tests
                   else "No es obligatorio agregar tests — el QA los corre.")
            )
        if config.require_commit_msg != default.require_commit_msg:
            lines.append(
                "## Commit message\n"
                + ("Generá COMMIT_MESSAGE.txt descriptivo." if config.require_commit_msg
                   else "Podés omitir COMMIT_MESSAGE.txt.")
            )

    if not lines:
        return ""

    header = (
        "\n\n---\n"
        "## 🛠️ Configuración personalizada del agente\n"
        "Las siguientes instrucciones vienen de la config del proyecto y "
        "SOBRESCRIBEN las reglas default de tu rol cuando entran en conflicto.\n"
    )
    return header + "\n\n".join(lines) + "\n"


def _tester_strictness_block(level: str) -> str:
    if level == "strict":
        return (
            "## Strictness: STRICT\n"
            "Sé exigente. Cualquier desvío del comportamiento esperado es un "
            "finding. Reportá incluso detalles cosméticos. Tu VEREDICTO "
            "default ante cualquier hallazgo es RECHAZADO salvo que sea "
            "puramente estético."
        )
    if level == "permissive":
        return (
            "## Strictness: PERMISSIVE\n"
            "Sé pragmático. Solo RECHAZADO si encontrás bloqueantes reales "
            "(no compila, crashea, corrompe datos o viola seguridad). Temas "
            "de estilo, performance leve, validaciones menores o mejoras "
            "de UX no-críticas van como ADVERTENCIAS en una sola sección "
            "'Observaciones menores' — NO bloquean. El VEREDICTO debe ser "
            "APROBADO o CON OBSERVACIONES salvo bloqueantes duros."
        )
    # normal → no hace falta inyectar (es el default)
    return ""


def _generic_strictness_block(level: str) -> str:
    if level == "strict":
        return (
            "## Strictness: STRICT\n"
            "Sé minucioso. Documentá riesgos, edge cases y dependencias con "
            "detalle. No des por hechos supuestos no verificados."
        )
    if level == "permissive":
        return (
            "## Strictness: PERMISSIVE\n"
            "Sé directo. Minimizá análisis exhaustivo si la tarea es clara. "
            "No bloquees por falta de detalle si lo esencial está cubierto."
        )
    return ""


def _tester_qa_block(config: AgentConfig) -> str:
    """Sección QA: scope de tests y criterios de clasificación."""
    default = AgentConfig()
    parts: list[str] = []

    if config.allowed_tests != default.allowed_tests:
        if "*" in config.allowed_tests:
            parts.append("Podés correr cualquier tipo de test.")
        else:
            parts.append(
                "Solo podés correr los siguientes tipos de test: "
                + ", ".join(f"`{t}`" for t in config.allowed_tests)
            )

    if config.forbidden_tests:
        parts.append(
            "NO corras los siguientes tipos de test (skippealos o marcá "
            "N/A con motivo 'skipped by config'): "
            + ", ".join(f"`{t}`" for t in config.forbidden_tests)
        )

    if config.blocker_criteria != default.blocker_criteria:
        parts.append(
            "Considerá BLOQUEANTE (=> RECHAZADO) únicamente estas clases: "
            + ", ".join(f"`{c}`" for c in config.blocker_criteria)
            + ". Cualquier otro hallazgo va como advisory."
        )

    if config.advisory_criteria != default.advisory_criteria:
        parts.append(
            "Considerá ADVISORY (=> CON OBSERVACIONES, no bloquea) estas "
            "clases: " + ", ".join(f"`{c}`" for c in config.advisory_criteria)
        )

    if config.auto_approve_with_observations != default.auto_approve_with_observations:
        if config.auto_approve_with_observations:
            parts.append(
                "CON OBSERVACIONES equivale a aprobado — el pipeline "
                "continúa a completado."
            )
        else:
            parts.append(
                "CON OBSERVACIONES debe ir a PM revisión (no se acepta "
                "automáticamente)."
            )

    if not parts:
        return ""

    return (
        "## Scope y criterios QA\n"
        + "\n".join(f"- {p}" for p in parts)
    )


# ── Export a dict para la UI ──────────────────────────────────────────────────

def to_dict(config: AgentConfig) -> dict:
    return asdict(config)


def from_dict(data: dict) -> AgentConfig:
    base = AgentConfig()
    known = set(asdict(base).keys())
    clean = {k: v for k, v in (data or {}).items() if k in known}
    # Coaccionar tipos comunes
    for bool_field in ("enabled", "auto_approve_with_observations",
                        "skip_queries", "require_analysis",
                        "require_tests", "require_commit_msg"):
        if bool_field in clean:
            clean[bool_field] = bool(clean[bool_field])
    for list_field in ("allowed_tests", "forbidden_tests",
                        "blocker_criteria", "advisory_criteria"):
        if list_field in clean and not isinstance(clean[list_field], list):
            clean[list_field] = []
    return AgentConfig(**{**asdict(base), **clean})
