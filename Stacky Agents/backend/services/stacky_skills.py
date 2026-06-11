"""stacky_skills.py — H4.2: servicio de Stacky Skills.

Lee archivos *.skill.md de backend/Stacky/skills/, los filtra por agente/proyecto
y los inyecta en el system prompt de los runtimes CLI (claude, codex, copilot).

Reutiliza el parser de frontmatter de services/vscode_agents.py.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_SKILLS_SUBDIR = "Stacky/skills"
_MAX_BODY_TOKENS = 1500   # cap duro al inyectar el cuerpo (aprox chars/4)
_MAX_BODY_CHARS = _MAX_BODY_TOKENS * 4  # 6000 chars


# ── Modelo ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    agents: tuple[str, ...]
    projects: tuple[str, ...]
    keywords: tuple[str, ...]
    body: str
    path: str


# ── Parser (reutiliza lógica de vscode_agents._parse_frontmatter) ─────────────


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Devuelve (frontmatter_dict, body). Si no hay frontmatter válido, dict vacío."""
    if text.startswith("﻿"):
        text = text.lstrip("﻿")
    if not text.startswith("---"):
        return {}, text
    rest = text[3:]
    if rest.startswith("\r\n"):
        rest = rest[2:]
    elif rest.startswith("\n"):
        rest = rest[1:]
    end = rest.find("\n---")
    if end < 0:
        return {}, text
    raw_fm = rest[:end]
    body_start = end + len("\n---")
    body = rest[body_start:]
    if body.startswith("\r\n"):
        body = body[2:]
    elif body.startswith("\n"):
        body = body[1:]
    try:
        fm = yaml.safe_load(raw_fm) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, body


def _to_tuple(value: object) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, str):
        return (value.strip().lower(),) if value.strip() else ()
    if isinstance(value, list):
        return tuple(str(v).strip().lower() for v in value if str(v).strip())
    return ()


def _parse_skill(path: Path) -> Skill | None:
    """Parsea un .skill.md; retorna None si el frontmatter es inválido/roto."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("skill: no se pudo leer %s: %s", path, exc)
        return None

    fm, body = _parse_frontmatter(text)

    name = str(fm.get("name") or "").strip()
    if not name:
        # Fallback: usar stem del archivo
        name = path.stem.replace(".skill", "")
    description = str(fm.get("description") or "").strip()
    agents = _to_tuple(fm.get("agents"))
    projects = _to_tuple(fm.get("projects"))
    keywords = _to_tuple(fm.get("keywords"))

    return Skill(
        name=name,
        description=description,
        agents=agents,
        projects=projects,
        keywords=keywords,
        body=body.strip(),
        path=str(path),
    )


# ── API pública ────────────────────────────────────────────────────────────────


def _skills_root(root: Path | None = None) -> Path:
    if root is not None:
        return root
    from runtime_paths import backend_root  # lazy — evita import circular
    return backend_root() / _SKILLS_SUBDIR


_cache: list[Skill] | None = None
_cache_root: Path | None = None


def load_skills(root: Path | None = None) -> list[Skill]:
    """Lee todos los *.skill.md de la carpeta skills/.

    Tolera frontmatter roto: skip + log, no crash. Resultado cacheado por root.
    """
    global _cache, _cache_root
    skills_dir = _skills_root(root)
    # Invalidar caché si cambia la raíz (útil en tests).
    if _cache is not None and _cache_root == skills_dir:
        return list(_cache)

    result: list[Skill] = []
    if not skills_dir.is_dir():
        logger.debug("skills: directorio no existe: %s", skills_dir)
        _cache, _cache_root = result, skills_dir
        return result

    for path in sorted(skills_dir.glob("*.skill.md")):
        skill = _parse_skill(path)
        if skill is None:
            logger.warning("skill: se omite %s (parse fallido)", path.name)
            continue
        result.append(skill)

    logger.debug("skills: cargadas %d skills desde %s", len(result), skills_dir)
    _cache, _cache_root = result, skills_dir
    return list(result)


def _clear_cache() -> None:
    """Limpia el caché en memoria (para tests)."""
    global _cache, _cache_root
    _cache = None
    _cache_root = None


def select_for_run(
    *,
    agent_type: str,
    project: str | None,
    context_text: str,
    max_skills: int = 3,
    root: Path | None = None,
) -> list[Skill]:
    """Filtra y rankea skills para el run actual.

    Filtros aplicados en orden:
    1. agents: vacío = todos; no vacío = agente debe estar en la lista.
    2. projects: vacío = todos; no vacío = proyecto debe estar en la lista.
    3. keywords: al menos 1 keyword presente (case-insensitive) en context_text.
       Si la skill no tiene keywords, se incluye siempre (pasa el filtro).

    Retorna hasta max_skills (cap = 3).
    """
    skills = load_skills(root)
    agent_lower = (agent_type or "").strip().lower()
    project_lower = (project or "").strip().lower()
    context_lower = (context_text or "").lower()

    result: list[Skill] = []
    for skill in skills:
        # Filtro por agente
        if skill.agents and agent_lower not in skill.agents:
            continue
        # Filtro por proyecto
        if skill.projects and project_lower not in skill.projects:
            continue
        # Filtro por keywords (si hay keywords, al menos una debe matchear)
        if skill.keywords:
            if not any(kw in context_lower for kw in skill.keywords):
                continue
        result.append(skill)
        if len(result) >= max_skills:
            break

    return result


def render_index(skills: list[Skill]) -> str:
    """Retorna el índice de skills en formato "- name: description\n" por skill."""
    if not skills:
        return ""
    lines = [f"- {s.name}: {s.description}" for s in skills]
    return "\n".join(lines)


def get_skill(name: str, root: Path | None = None) -> Skill | None:
    """Busca una skill por nombre exacto. Retorna None si no existe."""
    skills = load_skills(root)
    target = (name or "").strip().lower()
    for skill in skills:
        if skill.name.lower() == target:
            return skill
    return None


def cap_body(body: str) -> str:
    """Aplica el cap de 1500 tokens (~6000 chars) al cuerpo de una skill."""
    if len(body) <= _MAX_BODY_CHARS:
        return body
    return body[:_MAX_BODY_CHARS] + "\n\n[...skill truncada al cap de 1500 tokens]"
