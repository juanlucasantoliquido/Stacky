"""Plan 60 F0 — Diff PURO de ediciones HTML de work items ADO.

Función pura, sin red, sin BD. Idéntica en los 3 runtimes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_MIN_EDIT_CHARS = 12  # diff neto mínimo (chars) para considerar el cambio material


@dataclass(frozen=True)
class EditDelta:
    """Resultado del diff entre el baseline publicado por Stacky y la versión editada por el humano."""
    is_material: bool
    baseline_text: str          # baseline normalizado a texto plano
    edited_text: str            # edición normalizada a texto plano
    added_snippets: list[str]   # unidades presentes en edited y NO en baseline
    removed_snippets: list[str] # unidades presentes en baseline y NO en edited
    net_char_delta: int         # len(edited_text) - len(baseline_text)


def strip_html_to_text(html: str) -> str:
    """PURA. Quita tags HTML, decodifica entidades básicas, colapsa whitespace, trim."""
    text = str(html)
    # Entidades básicas
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&nbsp;", " ")
    text = text.replace("&#160;", " ")
    # Quitar tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Colapsar whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _split_units(text: str) -> list[str]:
    """PURA. Divide el texto en unidades (frases/líneas) para comparación."""
    # Primero por salto de línea, luego por '. ' (frase)
    parts: list[str] = []
    for line in text.splitlines():
        for sentence in re.split(r"\.\s+", line):
            stripped = sentence.strip().rstrip(".")
            if stripped:
                parts.append(stripped)
    return parts


def diff_edit(baseline_html: str, edited_html: str) -> EditDelta:
    """PURA. Normaliza ambos textos, compara por unidades y determina si el cambio es material.

    baseline vacío + edited no vacío → material.
    Solo whitespace diferente → no material.
    NUNCA lanza.
    """
    try:
        b = strip_html_to_text(baseline_html or "")
        e = strip_html_to_text(edited_html or "")

        if b == e:
            return EditDelta(
                is_material=False, baseline_text=b, edited_text=e,
                added_snippets=[], removed_snippets=[], net_char_delta=0,
            )

        b_units = _split_units(b)
        e_units = _split_units(e)
        b_set = set(b_units)
        e_set = set(e_units)
        added = [u for u in e_units if u not in b_set]
        removed = [u for u in b_units if u not in e_set]

        net_chars = sum(len(u) for u in added) + sum(len(u) for u in removed)
        is_material = net_chars > _MIN_EDIT_CHARS

        return EditDelta(
            is_material=is_material,
            baseline_text=b,
            edited_text=e,
            added_snippets=added,
            removed_snippets=removed,
            net_char_delta=len(e) - len(b),
        )
    except Exception:  # noqa: BLE001
        return EditDelta(
            is_material=False, baseline_text="", edited_text="",
            added_snippets=[], removed_snippets=[], net_char_delta=0,
        )
