"""cli_project_knowledge.py — F2.2: conocimiento del proyecto para el system
prompt del runtime claude_code_cli.

Porta al CLI lo que hoy solo recibe el path github_copilot vía
`agents/base.compose_system_prompt`: anti-patterns (FA-11), decisiones (FA-13),
constraints (FA-08) y glosario. Reusa los services existentes (no reimplementa
la lógica de relevancia) y aplica caps de tamaño.

Dueño único por tipo de conocimiento (anti doble inyección, B6 del plan):
  - anti-patterns / decisiones / constraints / glosario → ESTE módulo (system prompt).
  - client-profile → context_enrichment (bloque de contexto).
  - memoria colaborativa → context_enrichment (_inject_stacky_memory_block).
Acá NO se tocan client-profile ni memoria: cada uno tiene su único canal.

Función pura respecto a la DB de lectura; nunca lanza (cada fuente es
best-effort y se degrada con un warning).
"""
from __future__ import annotations

from typing import Any, Callable

LogFn = Callable[..., None]

# Cap de caracteres del bloque de conocimiento agregado al system prompt. Es un
# techo defensivo para no inflar el prompt del CLI; los services ya limitan por
# `limit=` el número de items.
_MAX_KNOWLEDGE_CHARS = 6000


def _noop(*_a: Any, **_k: Any) -> None:  # pragma: no cover - trivial
    pass


def build_project_knowledge_section(
    *,
    agent_type: str,
    project: str | None,
    context_text: str,
    log: LogFn | None = None,
) -> tuple[str, dict]:
    """Devuelve (texto_del_bloque, metadata_de_composicion).

    El texto va al final del system prompt del CLI (después de las reglas de
    Stacky). `metadata` registra cuántos items de cada tipo se inyectaron, para
    trazabilidad (paridad con sp_meta del path copilot).
    """
    log = log or _noop
    parts: list[str] = []
    meta: dict = {}

    # Anti-patterns (FA-11)
    try:
        from services import anti_patterns

        items = anti_patterns.relevant(agent_type=agent_type, project=project)
        meta["anti_patterns_count"] = len(items)
        if items:
            parts.append(anti_patterns.build_prefix(items))
    except Exception as exc:  # noqa: BLE001
        meta["anti_patterns_error"] = str(exc)

    # Decisiones (FA-13) — requieren context_text (matchea por tags)
    try:
        from services import decisions

        decs = decisions.relevant(project=project, context_text=context_text or "")
        meta["decisions_count"] = len(decs)
        if decs:
            parts.append(decisions.build_prefix(decs))
    except Exception as exc:  # noqa: BLE001
        meta["decisions_error"] = str(exc)

    # Constraints (FA-08)
    try:
        from services import constraints

        clist = constraints.relevant(
            agent_type=agent_type, project=project, context_text=context_text or ""
        )
        meta["constraints_count"] = len(clist)
        if clist:
            parts.append(constraints.build_prefix(clist))
    except Exception as exc:  # noqa: BLE001
        meta["constraints_error"] = str(exc)

    # Glosario detectado (términos del dominio en el contexto)
    try:
        from services import glossary

        gblock = glossary.build_glossary_block([context_text or ""])
        if gblock and (gblock.get("content") or "").strip():
            meta["glossary_terms"] = len(
                (gblock.get("source") or {}).get("terms") or []
            )
            parts.append(
                "## Glosario del dominio (términos detectados)\n"
                + gblock["content"].strip()
                + "\n"
            )
    except Exception as exc:  # noqa: BLE001
        meta["glossary_error"] = str(exc)

    if not parts:
        return "", meta

    section = "\n\n".join(p.strip() for p in parts if p.strip())
    if len(section) > _MAX_KNOWLEDGE_CHARS:
        section = section[:_MAX_KNOWLEDGE_CHARS].rstrip() + "\n\n[...conocimiento truncado por tamaño...]"
        meta["knowledge_truncated"] = True
    meta["knowledge_chars"] = len(section)
    log(
        "info",
        "conocimiento del proyecto inyectado al system prompt (F2.2): "
        f"anti_patterns={meta.get('anti_patterns_count', 0)}, "
        f"decisiones={meta.get('decisions_count', 0)}, "
        f"constraints={meta.get('constraints_count', 0)}, "
        f"glosario={meta.get('glossary_terms', 0)}",
    )
    return section, meta
