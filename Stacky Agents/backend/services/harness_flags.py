"""H0.4 — Registry declarativo de flags del arnés.

Reglas de diseño:
- PURO: no toca disco ni Flask. Solo describe y valida.
- Todo flag nuevo que introduzca el plan (H2/H3.3/H4/H5/H7) debe agregarse a
  FLAG_REGISTRY en el mismo PR que lo crea, para que aparezca en la UI sin
  tocar el frontend.
- env_only=True → el flag NO es atributo de Config; vive solo en os.environ
  (leído en call time, no en import time).
- El hot-apply lo hace el endpoint (api/harness_flags.py), no este módulo.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FlagSpec:
    key: str             # nombre EXACTO de la env var / atributo de Config
    type: str            # "bool" | "csv" | "int" | "float"
    label: str           # texto corto para la UI (español)
    description: str     # 1-2 líneas para tooltip
    group: str           # "claude_code_cli" | "global"
    pair: str | None = None    # key del *_PROJECTS asociado (UI los renderiza juntos)
    env_only: bool = False     # True = no existe como atributo de Config


FLAG_REGISTRY: tuple[FlagSpec, ...] = (
    FlagSpec(
        key="CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED",
        type="bool",
        label="Gate de contrato (claude)",
        description="F1.1 — Si ON, outputs con errores duros degradan el run a needs_review.",
        group="claude_code_cli",
    ),
    FlagSpec(
        key="CLAUDE_CODE_CLI_AUTOCORRECT_ENABLED",
        type="bool",
        label="Autocorrección stdin (claude)",
        description="F1.3 — Loop de autocorrección al fin de cada turno via stdin.",
        group="claude_code_cli",
    ),
    FlagSpec(
        key="CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES",
        type="int",
        label="Max reintentos autocorrección",
        description="Máximo de mensajes correctivos por run (default 2).",
        group="claude_code_cli",
    ),
    FlagSpec(
        key="CLAUDE_CODE_CLI_HOOKS_ENABLED",
        type="bool",
        label="Hooks PostToolUse (claude)",
        description="F1.4 — settings.json efímero con hook de validación de artifacts.",
        group="claude_code_cli",
    ),
    FlagSpec(
        key="CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_ENABLED",
        type="bool",
        label="Conocimiento de proyecto (claude)",
        description="F2.2 — Anti-patrones/decisiones/constraints/glosario en el system prompt.",
        group="claude_code_cli",
        pair="CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_PROJECTS",
    ),
    FlagSpec(
        key="CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_PROJECTS",
        type="csv",
        label="Proyectos — conocimiento",
        description="Allowlist CSV de proyectos. Vacío = todos (escape hatch).",
        group="claude_code_cli",
    ),
    FlagSpec(
        key="CLAUDE_CODE_CLI_RESUME_ENABLED",
        type="bool",
        label="Resume de sesión (claude)",
        description="F2.3 — Re-runs con --resume + delta prompt.",
        group="claude_code_cli",
        pair="CLAUDE_CODE_CLI_RESUME_PROJECTS",
    ),
    FlagSpec(
        key="CLAUDE_CODE_CLI_RESUME_PROJECTS",
        type="csv",
        label="Proyectos — resume",
        description="Allowlist CSV de proyectos. Vacío = todos.",
        group="claude_code_cli",
    ),
    FlagSpec(
        key="CLAUDE_CODE_CLI_MCP_ENABLED",
        type="bool",
        label="MCP server (claude)",
        description="F2.1 — Stacky MCP server inyectado vía --mcp-config.",
        group="claude_code_cli",
        pair="CLAUDE_CODE_CLI_MCP_PROJECTS",
    ),
    FlagSpec(
        key="CLAUDE_CODE_CLI_MCP_PROJECTS",
        type="csv",
        label="Proyectos — MCP",
        description="Allowlist CSV de proyectos. Vacío = todos.",
        group="claude_code_cli",
    ),
    FlagSpec(
        key="STACKY_CONTEXT_BUDGET_ENABLED",
        type="bool",
        label="Presupuesto de contexto",
        description="F2.4 — Ranking + truncado de bloques de contexto.",
        group="global",
        pair="STACKY_CONTEXT_BUDGET_PROJECTS",
    ),
    FlagSpec(
        key="STACKY_CONTEXT_BUDGET_PROJECTS",
        type="csv",
        label="Proyectos — budget contexto",
        description="Allowlist CSV de proyectos. Vacío = todos.",
        group="global",
    ),
    FlagSpec(
        key="STACKY_CONTEXT_BUDGET_TOKENS",
        type="int",
        label="Tokens máx contexto",
        description="Presupuesto global de tokens estimados (default 25000).",
        group="global",
    ),
    FlagSpec(
        key="STACKY_MEMORY_INJECTION_ENABLED",
        type="bool",
        label="Inyección de memoria colaborativa",
        description="F2.5 — Inyecta observaciones curadas en el user prompt.",
        group="global",
        pair="STACKY_MEMORY_INJECTION_PROJECTS",
        env_only=True,  # leído de os.environ en call time, no atributo de Config
    ),
    FlagSpec(
        key="STACKY_MEMORY_INJECTION_PROJECTS",
        type="csv",
        label="Proyectos — memoria",
        description="Allowlist CSV de proyectos. Vacío = todos.",
        group="global",
    ),
    # ── H3.3 — Egress check para runtimes CLI ────────────────────────────────
    FlagSpec(
        key="STACKY_CLI_EGRESS_ENABLED",
        type="bool",
        label="Egress check en CLI (claude + codex)",
        description=(
            "H3.3 — Si ON, corre egress_policies.check sobre el prompt final de cada "
            "runtime CLI antes de hacer spawn. Si bloquea, el run termina con error."
        ),
        group="global",
        env_only=True,  # leído de os.environ en call time, no atributo de Config
    ),
    # ── H2 — Paridad codex_cli ────────────────────────────────────────────────
    FlagSpec(
        key="CODEX_CLI_CONTRACT_GATE_ENABLED",
        type="bool",
        label="Gate de contrato (codex)",
        description="H2.1 — Si ON, outputs con errores duros degradan el run a needs_review.",
        group="codex_cli",
    ),
    FlagSpec(
        key="CODEX_CLI_AUTOCORRECT_ENABLED",
        type="bool",
        label="Autocorrección exec resume (codex)",
        description="H2.3 — Loop de autocorrección al fin del run via codex exec resume.",
        group="codex_cli",
    ),
    FlagSpec(
        key="CODEX_CLI_AUTOCORRECT_MAX_RETRIES",
        type="int",
        label="Max reintentos autocorrección (codex)",
        description="Máximo de resumes correctivos por run codex (default 2).",
        group="codex_cli",
    ),
    FlagSpec(
        key="CODEX_CLI_MODEL_DENYLIST",
        type="csv",
        label="Denylist de modelos (codex)",
        description="H2.4 — CSV de modelos codex bloqueados; si matchea degrada a CODEX_CLI_MODEL.",
        group="codex_cli",
    ),
    # ── H4 — Stacky Skills ────────────────────────────────────────────────────
    FlagSpec(
        key="STACKY_SKILLS_ENABLED",
        type="bool",
        label="Stacky Skills (todos los runtimes)",
        description=(
            "H4.3 — Si ON, inyecta el índice/cuerpo de skills relevantes en el "
            "system prompt de claude, codex y copilot antes de _STACKY_RULES."
        ),
        group="global",
        pair="STACKY_SKILLS_PROJECTS",
    ),
    FlagSpec(
        key="STACKY_SKILLS_PROJECTS",
        type="csv",
        label="Proyectos — Skills",
        description="Allowlist CSV de proyectos. Vacío = todos.",
        group="global",
    ),
    # ── H7 — Resume unificado (codex) ────────────────────────────────────────
    FlagSpec(
        key="CODEX_CLI_RESUME_ENABLED",
        type="bool",
        label="Resume de sesión (codex)",
        description="H7.1 — Re-runs con codex exec resume + delta prompt (paridad con claude F2.3).",
        group="codex_cli",
        pair="CODEX_CLI_RESUME_PROJECTS",
    ),
    FlagSpec(
        key="CODEX_CLI_RESUME_PROJECTS",
        type="csv",
        label="Proyectos — resume (codex)",
        description="Allowlist CSV de proyectos. Vacío = todos.",
        group="codex_cli",
    ),
    # ── H5 — Runaway guard in-run ─────────────────────────────────────────────
    FlagSpec(
        key="STACKY_RUNAWAY_MAX_TURNS",
        type="int",
        label="Runaway: turnos máx por run",
        description=(
            "H5 — Máximo de turnos por run agéntico. 0 = sin límite (desactivado). "
            "Al superar: señal de cierre + needs_review."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_RUNAWAY_MAX_COST_USD",
        type="float",
        label="Runaway: costo máx por run (USD)",
        description=(
            "H5 — Costo máximo en USD por run agéntico. 0.0 = sin límite (desactivado). "
            "Solo disponible en claude (codex no reporta costo en stream)."
        ),
        group="global",
    ),
)

# Índice rápido para lookups O(1)
_REGISTRY_INDEX: dict[str, FlagSpec] = {s.key: s for s in FLAG_REGISTRY}


def read_current() -> list[dict]:
    """Devuelve spec + valor actual de cada flag del registry."""
    from config import config

    result = []
    for spec in FLAG_REGISTRY:
        if spec.env_only:
            raw = os.getenv(spec.key)
            if raw is None:
                value: object = (
                    False if spec.type == "bool"
                    else ("" if spec.type == "csv"
                    else (0.0 if spec.type == "float"
                    else 0))
                )
            else:
                value = _cast(spec, raw)
        else:
            value = getattr(config, spec.key)

        result.append({
            "key": spec.key,
            "type": spec.type,
            "label": spec.label,
            "description": spec.description,
            "group": spec.group,
            "pair": spec.pair,
            "env_only": spec.env_only,
            "value": value,
        })
    return result


def apply_updates(updates: dict[str, object]) -> dict[str, object]:
    """Valida y castea los valores recibidos.

    Returns:
        Dict con los valores tipados y listos para persistir/aplicar.

    Raises:
        ValueError: si alguna key no está en el registry, o el valor no puede
            castearse al tipo declarado.

    No persiste ni aplica (eso es responsabilidad del endpoint).
    """
    result: dict[str, object] = {}
    for key, raw_value in updates.items():
        if key not in _REGISTRY_INDEX:
            raise ValueError(
                f"Flag desconocida: {key!r}. Solo se aceptan keys registradas en FLAG_REGISTRY."
            )
        spec = _REGISTRY_INDEX[key]
        result[key] = _cast(spec, raw_value)
    return result


def _cast(spec: FlagSpec, raw: object) -> object:
    """Castea `raw` al tipo declarado por `spec`. Lanza ValueError si no puede."""
    if spec.type == "bool":
        if isinstance(raw, bool):
            return raw
        s = str(raw).strip().lower()
        if s in ("1", "true", "yes", "on"):
            return True
        if s in ("0", "false", "no", "off", ""):
            return False
        raise ValueError(
            f"Flag {spec.key!r}: valor no válido para bool: {raw!r}. "
            "Usar true/false, 1/0, yes/no."
        )
    if spec.type == "csv":
        # Normalizar: trim por elemento, trailing comas eliminadas
        parts = [p.strip() for p in str(raw).split(",") if p.strip()]
        return ",".join(parts)
    if spec.type == "int":
        try:
            return int(str(raw).strip())
        except (ValueError, TypeError):
            raise ValueError(
                f"Flag {spec.key!r}: valor no válido para int: {raw!r}."
            )
    if spec.type == "float":
        try:
            return float(str(raw).strip())
        except (ValueError, TypeError):
            raise ValueError(
                f"Flag {spec.key!r}: valor no válido para float: {raw!r}."
            )
    raise ValueError(f"Tipo desconocido en FLAG_REGISTRY para {spec.key!r}: {spec.type!r}")
