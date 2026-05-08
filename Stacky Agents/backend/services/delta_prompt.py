"""
FA-32 — Diff-based re-execution.

Cuando un operador re-corre un agente con un cambio PEQUEÑO en el contexto
(< 30% del contenido total cambia), en lugar de re-procesar todo, enviamos
un prompt delta que le dice al agente:

  "Este es tu output anterior. El contexto cambió en lo siguiente: [diff].
   Actualizá sólo las secciones afectadas."

Esto reduce tokens hasta 5x y es más preciso porque el agente sabe QUÉ cambió.

Implementación:
- `compute_diff(old_blocks, new_blocks)` → DiffResult con ratio y bloques cambiados
- `build_delta_prompt(old_output, diff)` → prompt de actualización parcial
- Si ratio >= 0.30 → no aplica delta, usar re-run completo normal
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass


@dataclass
class BlockDiff:
    block_id: str
    title: str
    kind: str   # "added" | "removed" | "modified"
    old_content: str
    new_content: str


@dataclass
class DiffResult:
    change_ratio: float          # 0.0 = sin cambios, 1.0 = todo cambió
    changed_blocks: list[BlockDiff]
    is_delta_eligible: bool       # True si ratio < 0.30


def _block_text(block: dict) -> str:
    parts: list[str] = []
    if block.get("title"):
        parts.append(block["title"])
    if isinstance(block.get("content"), str):
        parts.append(block["content"])
    for it in block.get("items") or []:
        if it.get("selected"):
            parts.append(it.get("label", ""))
    return "\n".join(parts)


def _char_diff_ratio(old: str, new: str) -> float:
    if not old and not new:
        return 0.0
    if not old or not new:
        return 1.0
    sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
    return 1.0 - sm.ratio()


def compute_diff(old_blocks: list[dict], new_blocks: list[dict]) -> DiffResult:
    old_map = {b["id"]: b for b in old_blocks if isinstance(b.get("id"), str)}
    new_map = {b["id"]: b for b in new_blocks if isinstance(b.get("id"), str)}

    changed: list[BlockDiff] = []
    all_ids = set(old_map) | set(new_map)
    total_chars = 0
    changed_chars = 0

    for bid in all_ids:
        old_b = old_map.get(bid)
        new_b = new_map.get(bid)
        old_text = _block_text(old_b) if old_b else ""
        new_text = _block_text(new_b) if new_b else ""
        total_chars += max(len(old_text), len(new_text), 1)

        if old_text == new_text:
            continue

        diff_chars = int(abs(len(old_text) - len(new_text)) +
                         len(old_text) * _char_diff_ratio(old_text, new_text))
        changed_chars += diff_chars

        if old_b and not new_b:
            kind = "removed"
        elif not old_b and new_b:
            kind = "added"
        else:
            kind = "modified"

        changed.append(BlockDiff(
            block_id=bid,
            title=(new_b or old_b or {}).get("title", bid),
            kind=kind,
            old_content=old_text,
            new_content=new_text,
        ))

    ratio = min(1.0, changed_chars / max(1, total_chars))
    return DiffResult(
        change_ratio=round(ratio, 3),
        changed_blocks=changed,
        is_delta_eligible=ratio < 0.30 and len(changed) > 0,
    )


def build_delta_prompt(previous_output: str, diff: DiffResult) -> str:
    """
    Construye un prompt que le pide al agente actualizar sólo las secciones
    afectadas del output previo.
    """
    changes_desc: list[str] = []
    for bc in diff.changed_blocks:
        if bc.kind == "added":
            changes_desc.append(
                f"- **{bc.title}** fue AGREGADO al contexto:\n{bc.new_content[:400]}"
            )
        elif bc.kind == "removed":
            changes_desc.append(f"- **{bc.title}** fue ELIMINADO del contexto.")
        else:
            diff_preview = _unified_diff_preview(bc.old_content, bc.new_content)
            changes_desc.append(
                f"- **{bc.title}** fue MODIFICADO:\n{diff_preview}"
            )

    return (
        "## Contexto de re-ejecución incremental\n\n"
        "Este es tu output anterior:\n\n"
        f"```\n{previous_output[:3000]}\n```\n\n"
        "El contexto cambió en los siguientes puntos "
        f"({diff.change_ratio:.0%} del total):\n\n"
        + "\n\n".join(changes_desc)
        + "\n\n**Instrucción:** Actualizá SOLO las secciones de tu output que se ven afectadas "
        "por estos cambios. Mantené el resto idéntico. "
        "Si el cambio es irrelevante para tu análisis, indicalo explícitamente.\n\n"
        "## Nuevo contexto completo\n"
    )


def _unified_diff_preview(old: str, new: str, max_lines: int = 8) -> str:
    old_lines = old.splitlines(keepends=True)[:20]
    new_lines = new.splitlines(keepends=True)[:20]
    diff = list(difflib.unified_diff(old_lines, new_lines, n=1))[:max_lines]
    if not diff:
        return "(cambio menor)"
    return "```diff\n" + "".join(diff) + "\n```"
