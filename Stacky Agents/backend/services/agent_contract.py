"""Plan 133 F5 — Contrato declarativo de bloques requeridos por agente.

Sintaxis del frontmatter (`.agent.md`):

    stacky_required_blocks: "ado-epic-structured|ado-blocker, client-profile"

Semántica: lista separada por comas = AND; dentro de cada término, `|` = OR
de alternativas. El ejemplo exige (`ado-epic-structured` O `ado-blocker`) Y
(`client-profile`).
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("stacky.services.agent_contract")

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


class AgentContractError(RuntimeError):
    """Bloques requeridos ausentes tras el enriquecimiento (pre-spawn)."""


def parse_required_blocks(agent_md_text: str) -> list[list[str]]:
    """Extrae stacky_required_blocks del frontmatter YAML-lite.

    Parser k:v línea a línea entre los dos '---' (mismo enfoque que
    tests/test_business_agent_bundled.py:16 _parse_frontmatter, sin
    dependencia de PyYAML). Sin frontmatter o sin la clave → [].
    "a|b, c" → [["a","b"],["c"]]. Espacios y comillas se strippean;
    términos vacíos se ignoran.
    """
    if not agent_md_text:
        return []
    m = _FRONTMATTER_RE.match(agent_md_text)
    if not m:
        return []
    raw_value: str | None = None
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        if key.strip() == "stacky_required_blocks":
            raw_value = value.strip().strip('"').strip("'")
            break
    if not raw_value:
        return []
    groups: list[list[str]] = []
    for term in raw_value.split(","):
        alternatives = [
            alt.strip().strip('"').strip("'")
            for alt in term.split("|")
        ]
        alternatives = [a for a in alternatives if a]
        if alternatives:
            groups.append(alternatives)
    return groups


def resolve_agent_md_text(vscode_agent_filename: str) -> str | None:
    """Lee el .agent.md con la MISMA resolución de ruta que el runner de Claude
    (claude_code_cli_runner.py): Path(config.VSCODE_PROMPTS_DIR)/filename,
    fallback services.stacky_agents.stacky_agents_dir(). No existe → None.
    """
    from pathlib import Path

    from config import config
    from services import stacky_agents as stacky_agents_svc

    candidates = []
    try:
        candidates.append(Path(config.VSCODE_PROMPTS_DIR) / vscode_agent_filename)
    except Exception:  # noqa: BLE001 — VSCODE_PROMPTS_DIR puede lanzar en entornos raros
        pass
    try:
        candidates.append(stacky_agents_svc.stacky_agents_dir() / vscode_agent_filename)
    except Exception:  # noqa: BLE001
        pass

    for path in candidates:
        try:
            if path.exists():
                return path.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
    return None


def enforce(*, vscode_agent_filename: str | None, blocks: list[dict]) -> None:
    """Valida post-enrichment que los bloques declarados obligatorios estén presentes.

    No-op (no levanta) cuando: flag STACKY_REQUIRED_BLOCKS_ENABLED OFF,
    vscode_agent_filename None o vacío (github_copilot puede correr sin agente
    VS Code: agent_runner.py `vscode_agent_filename: str | None = None`),
    archivo ausente, o `stacky_required_blocks` vacío/no declarado.

    Fail-closed SOLO en la ausencia determinista de un grupo requerido
    (levanta AgentContractError). Cualquier error propio inesperado del
    parseo/resolución → no-op con log.warning (best-effort).
    """
    from config import config

    if not getattr(config, "STACKY_REQUIRED_BLOCKS_ENABLED", False):
        return
    if not vscode_agent_filename:
        return

    try:
        text = resolve_agent_md_text(vscode_agent_filename)
        if not text:
            return
        required = parse_required_blocks(text)
        if not required:
            return
        present_ids = {b.get("id") for b in (blocks or []) if isinstance(b, dict)}
    except Exception as exc:  # noqa: BLE001 — best-effort en el parseo/resolución
        logger.warning(
            "agent_contract.enforce — error inesperado (no-op): %s", exc
        )
        return

    for group in required:
        if not any(alt in present_ids for alt in group):
            group_label = "|".join(group)
            raise AgentContractError(
                f"El agente {vscode_agent_filename} requiere el bloque {group_label} "
                "en el contexto y el enriquecimiento no lo produjo. Causas típicas: "
                "ticket sin épica/bloqueante (corré el preflight), client-profile no "
                "configurado, o tracker inaccesible."
            )
