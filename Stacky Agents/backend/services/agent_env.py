"""
agent_env.py — Construcción del entorno (env vars) para subprocesos de agente.

REGLA CRÍTICA (Fase 3c, plan PLAN-stacky-agents-state-sync-ado-delegation.md):
Los subprocesos del agente (Codex CLI, VS Code Copilot bridge, etc.) NO deben
recibir credenciales que les permitan publicar en Azure DevOps directamente.

Este módulo es el único punto autorizado para construir el environ que se
pasa a `subprocess.Popen(env=...)` cuando se lanza un agente.

Variables filtradas (denylist):
    ADO_PAT, AZURE_PAT, AZURE_DEVOPS_PAT, AZURE_DEVOPS_EXT_PAT
    SYSTEM_ACCESSTOKEN  (token de pipelines de ADO)
    GIT_ASKPASS_PAT     (cualquier variante "*_PAT")
    AGENT_TOKENS, SERVICE_PRINCIPAL_*
    BASIC_AUTH, COPILOT_TOKEN (compartir con el agente sería un secret leak)

Cualquier variable cuyo nombre contenga 'PAT', 'TOKEN', 'SECRET', 'PASSWORD'
también se filtra por heurística — esto es un guardrail amplio. Las
excepciones legítimas se pueden agregar a `ALLOWED_TOKEN_NAMES`.
"""
from __future__ import annotations

import logging
import os
from typing import Mapping

logger = logging.getLogger("stacky.agent_env")


# Denylist exacta (case-insensitive). Estas variables siempre se quitan.
_EXACT_DENY: frozenset[str] = frozenset({
    "ADO_PAT",
    "AZURE_PAT",
    "AZURE_DEVOPS_PAT",
    "AZURE_DEVOPS_EXT_PAT",
    "SYSTEM_ACCESSTOKEN",
    "SYSTEM_ACCESS_TOKEN",
    "GITHUB_TOKEN",          # GitHub PAT no autorizado para agente
    "GIT_ASKPASS_PAT",
    "COPILOT_TOKEN",         # se inyecta solo si el agente lo necesita explícitamente
    "STACKY_PAT",
    "BASIC_AUTH",
    "OPENAI_API_KEY",        # gestionado por codex_cli a través de su config propia
    "ANTHROPIC_API_KEY",
})

# Heurística de patrones de nombres. Si el nombre contiene alguno de estos
# substrings (case-insensitive) Y no está en la allowlist, se filtra.
_PATTERN_DENY: tuple[str, ...] = (
    "PAT", "TOKEN", "SECRET", "PASSWORD", "PASSWD",
    "PRIVATE_KEY", "API_KEY", "APIKEY", "BEARER",
)

# Allowlist explícita: variables que cumplen el patrón pero son seguras o
# necesarias para que el agente funcione (p.ej. ruta de tokens en disco que
# el agente espera abrir manualmente — no son el secreto en sí).
_ALLOWLIST: frozenset[str] = frozenset({
    "PATH",  # contiene "PAT" pero es obvio que se necesita
    "PATHEXT",
    "PATHEXT2",
})


def build_agent_env(
    base: Mapping[str, str] | None = None,
    *,
    extra: Mapping[str, str] | None = None,
    extra_deny: Mapping[str, None] | set[str] | None = None,
) -> dict[str, str]:
    """Construye un environ filtrado para lanzar el subproceso de un agente.

    Args:
        base: env base sobre el que filtrar. Default: `os.environ`.
        extra: variables a inyectar luego del filtro (p.ej. STACKY_AGENT_RUN_ID).
        extra_deny: variables adicionales a quitar (set de nombres).

    Returns:
        Nuevo dict con las variables filtradas; el `base` no se modifica.
    """
    source: Mapping[str, str] = base if base is not None else os.environ
    extra_deny_set: set[str] = set()
    if extra_deny:
        extra_deny_set = (
            set(extra_deny) if isinstance(extra_deny, set)
            else set(extra_deny.keys())
        )
    extra_deny_upper = {x.upper() for x in extra_deny_set}

    out: dict[str, str] = {}
    removed: list[str] = []
    for k, v in source.items():
        upper = k.upper()
        if upper in _ALLOWLIST:
            out[k] = v
            continue
        if upper in _EXACT_DENY or upper in extra_deny_upper:
            removed.append(k)
            continue
        if any(p in upper for p in _PATTERN_DENY):
            removed.append(k)
            continue
        out[k] = v

    if extra:
        out.update(extra)

    if removed:
        # No loguear los valores — solo nombres.
        logger.info(
            "agent_env: filtradas %d variables sensibles: %s",
            len(removed),
            ", ".join(sorted(set(removed))),
        )
    return out


def is_denied(name: str) -> bool:
    """Helper para tests / inspección puntual."""
    upper = name.upper()
    if upper in _ALLOWLIST:
        return False
    if upper in _EXACT_DENY:
        return True
    return any(p in upper for p in _PATTERN_DENY)
