"""F0/F1 (plan 48) — Memoria que Empuja: convierte memorias `operator_note` de
veredictos rechazados/condicionados en ítems de anti-patrón imperativos.

PURO respecto de red/DB/Flask en build_items/build_prefix (reciben/devuelven
dicts y dataclasses). load_for_run lee memory_store (best-effort). La inyección
vive en F2 (context_enrichment, runtimes CLI) y F3 (agents/base, github_copilot).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RejectionItem:
    """Shape compatible con anti_patterns._Loaded (.pattern, .reason, .example).

    Se replica el shape para no importar la dataclass interna y evitar acoplamiento.
    """
    pattern: str
    reason: str
    example: str | None = None


# Tags que marcan una memoria como lección de rechazo (los setea capture_operator_note).
REJECTION_TAGS = ("rejected_reason", "approval_condition")
_MAX_ITEMS = 6          # techo de lecciones inyectadas (poda; idea 4 fusionada)
_MAX_PATTERN_CHARS = 280
_MAX_REASON_CHARS = 280


def _norm(text: str) -> str:
    """Normaliza para dedupe: minúsculas, espacios colapsados."""
    return " ".join((text or "").lower().split())


def build_items(
    memories: list[dict],
    *,
    existing_patterns: set[str] | None = None,
    max_items: int = _MAX_ITEMS,
) -> list[RejectionItem]:
    """Convierte memorias operator_note en ítems de anti-patrón.

    - `memories`: dicts con al menos {'content', 'tags', 'title'} (memory_store.to_dict).
      Se asume YA ordenadas por recencia DESC por el caller (F1).
    - Solo procesa memorias cuyo `tags` intersecta REJECTION_TAGS.
    - `existing_patterns`: set de patrones normalizados ya inyectados por FA-11
      (dedupe cruzado, principio 8). Se saltean coincidencias.
    - Trunca pattern/reason; descarta vacíos; corta en max_items.
    - El `content` de operator_note tiene forma "Veredicto: X\\n\\n<nota>".
      El pattern es la primera línea no vacía de la nota; el reason es el contexto.
    """
    seen = set(existing_patterns or set())
    out: list[RejectionItem] = []
    for m in memories:
        if len(out) >= max_items:
            break
        tags = m.get("tags") or []
        if not any(t in REJECTION_TAGS for t in tags):
            continue
        content = (m.get("content") or "").strip()
        if not content:
            continue
        # Separar "Veredicto: X" del cuerpo de la nota.
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        note_lines = [ln for ln in lines if not ln.lower().startswith("veredicto:")]
        if not note_lines:
            continue
        pattern = note_lines[0][:_MAX_PATTERN_CHARS]
        key = _norm(pattern)
        if not key or key in seen:
            continue
        seen.add(key)
        rest = " ".join(note_lines[1:]).strip()
        reason = (
            rest
            or "El operador rechazó/condicionó un output por este motivo en este proyecto."
        )[:_MAX_REASON_CHARS]
        out.append(RejectionItem(pattern=pattern, reason=reason, example=None))
    return out


def build_prefix(items: list[RejectionItem]) -> str:
    """Render imperativo, mismo formato que anti_patterns.build_prefix pero con
    encabezado que aclara el origen (rechazos del operador)."""
    if not items:
        return ""
    body_lines = []
    for i, it in enumerate(items, 1):
        body_lines.append(f"{i}. **Evitá**: {it.pattern}\n   **Por qué**: {it.reason}")
    return (
        "## Lecciones de rechazos previos (el operador YA rechazó esto en este proyecto)\n"
        "Estos motivos causaron rechazo o aprobación condicionada en runs anteriores. "
        "Tratalos como restricciones duras: NO repitas estos errores.\n\n"
        + "\n\n".join(body_lines)
        + "\n"
    )


def load_for_run(
    *,
    project: str | None,
    agent_type: str | None,
    existing_patterns: set[str] | None = None,
    max_items: int = _MAX_ITEMS,
) -> list[RejectionItem]:
    """Carga memorias operator_note del proyecto y construye RejectionItems.

    - project None → [] (no hay contexto de proyecto).
    - Reusa memory_store.list_observations (filtra type/status/project, ordena por
      updated_at DESC, devuelve dicts con `tags` lista). El corte fino por
      REJECTION_TAGS lo hace build_items.
    - agent_type: NO se exige (una lección de rechazo del proyecto puede aplicar a
      otro agente del mismo proyecto). El filtro por tags hace el recorte.
    - Best-effort: cualquier excepción → [].
    """
    if not project:
        return []
    try:
        from services import memory_store
        memories = memory_store.list_observations(
            project=project,
            status="active",
            type="operator_note",
            limit=50,
        )
    except Exception:  # noqa: BLE001
        return []
    return build_items(
        memories, existing_patterns=existing_patterns, max_items=max_items
    )


# ---------------------------------------------------------------------------
# Plan 54 F4 — Sink determinístico (nota → corpus)
# ---------------------------------------------------------------------------

def pure_rejection_to_lesson(note: str) -> str:
    """Convierte una nota de rechazo en una lección imperativa determinista.

    PURA: misma nota → mismo resultado. Sin LLM, sin red.
    nota vacía → "".
    """
    stripped = (note or "").strip()
    if not stripped:
        return ""
    return f"NO REPITAS: {stripped}"


# ---------------------------------------------------------------------------
# Plan 54 F4b — Poda determinística del corpus
# ---------------------------------------------------------------------------

def trim_rejection_corpus(
    *,
    project: str,
    agent_type: str,
    max_count: int = 100,
) -> int:
    """Mantiene solo las últimas max_count lecciones de rechazo (por updated_at DESC).

    Elimina filas con índice ≥ max_count en el ordenamiento DESC.
    Devuelve el número de filas eliminadas.
    PURA respecto de lógica de negocio; lee/escribe memory_store via DB.
    Best-effort: cualquier excepción → 0 (nunca bloquea).
    """
    if not project:
        return 0
    try:
        from services import memory_store  # noqa: PLC0415
        rows = memory_store.list_observations(
            project=project,
            status="active",
            type="operator_note",
            limit=max_count + 200,  # trae más para poder podar
        )
        # Filtrar solo las que tienen tags de rechazo
        rejection_rows = [
            r for r in rows
            if any(t in REJECTION_TAGS for t in (r.get("tags") or []))
        ]
        # Las primeras max_count se conservan (asumimos list_observations ordena DESC)
        to_delete = rejection_rows[max_count:]
        if not to_delete:
            return 0
        deleted = 0
        for row in to_delete:
            mem_id = row.get("memory_id")
            if mem_id:
                try:
                    memory_store.set_status(mem_id, "deleted")
                    deleted += 1
                except Exception:  # noqa: BLE001
                    pass
        return deleted
    except Exception:  # noqa: BLE001
        return 0
