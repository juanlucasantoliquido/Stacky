"""
FA-37 — PII auto-masking pre-prompt + logs.

Antes de mandar texto al LLM, enmascaramos identificadores personales
con tokens reversibles. Después de recibir el output, des-enmascaramos
para que el operador vea los datos correctos en la UI.

Patrones cubiertos (Argentina/Pacífico):
- DNI (7-8 dígitos)
- CUIT/CUIL (XX-XXXXXXXX-X)
- Email
- Teléfono (+54 9 11 1234-5678 y variantes)
- Tarjeta de crédito (16 dígitos con/sin separadores)
- IBAN/CBU (22 dígitos)

Diseño:
- `mask(text, [mask_map])` → texto masked + map dict { token: original }
- `unmask(text, mask_map)` → texto con originales restaurados
- `mask_blocks(blocks)` → enmascara recursivamente content / items.label

Política: el map vive en memoria por la duración del Run. NUNCA se persiste.
Solo el texto ya enmascarado puede ir a cache / logs / few-shot.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Patrones — orden importa (de más específico a más general)
# ---------------------------------------------------------------------------

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("CUIT", re.compile(r"\b\d{2}-\d{8}-\d\b")),
    ("CBU", re.compile(r"\b\d{22}\b")),
    ("CARD", re.compile(r"\b(?:\d{4}[\s-]?){3}\d{4}\b")),
    ("PHONE", re.compile(r"\+?\d{1,3}[\s-]?\(?\d{1,4}\)?[\s-]?\d{2,4}[\s-]?\d{3,4}(?:[\s-]?\d{2,4})?")),
    ("DNI", re.compile(r"\b\d{7,8}\b")),
]


@dataclass
class MaskResult:
    text: str
    map: dict[str, str]  # token → original


def mask(text: str, existing_map: dict[str, str] | None = None) -> str:
    """Versión side-effect-free que reusa un map ya construido (para output→cache)."""
    if not text or not existing_map:
        return text
    out = text
    # Reemplazar los originales por sus tokens (ya que el map fue construido con originales→tokens
    # invertimos para mask).
    for token, original in existing_map.items():
        out = out.replace(original, token)
    return out


def mask_text(text: str, mask_map: dict[str, str] | None = None) -> tuple[str, dict[str, str]]:
    """
    Enmascara `text`. Si pasás `mask_map`, reusa tokens ya asignados (consistencia
    cross-bloques: el mismo email recibe el mismo token).
    Devuelve (masked_text, map { token: original }).
    """
    if not text:
        return text, mask_map or {}
    mp: dict[str, str] = dict(mask_map or {})
    # invertimos para tener original → token
    inv: dict[str, str] = {orig: tok for tok, orig in mp.items()}

    counter = max(
        [int(k.split("_")[-1].rstrip("Z")) for k in mp.keys() if k.startswith("ZZZ_PII_")]
        + [0]
    )

    out = text
    for kind, rx in PATTERNS:
        def _sub(match: re.Match[str]) -> str:
            nonlocal counter
            original = match.group(0)
            if original in inv:
                return inv[original]
            counter += 1
            token = f"ZZZ_PII_{kind}_{counter:04d}Z"
            inv[original] = token
            mp[token] = original
            return token
        out = rx.sub(_sub, out)
    return out, mp


def mask_blocks(blocks: list[dict]) -> tuple[list[dict], dict[str, str]]:
    """Enmascara content e items.label; mantiene el resto intacto.
    Devuelve (blocks_masked, map). El map cubre TODOS los bloques (consistencia)."""
    if not blocks:
        return blocks, {}
    mp: dict[str, str] = {}
    out: list[dict] = []
    for b in blocks:
        new_b = dict(b)
        if isinstance(new_b.get("content"), str):
            new_b["content"], mp = mask_text(new_b["content"], mp)
        if new_b.get("items"):
            new_items = []
            for it in new_b["items"]:
                new_it = dict(it)
                if isinstance(new_it.get("label"), str):
                    new_it["label"], mp = mask_text(new_it["label"], mp)
                new_items.append(new_it)
            new_b["items"] = new_items
        out.append(new_b)
    return out, mp


def unmask(text: str, mask_map: dict[str, str] | None) -> str:
    if not text or not mask_map:
        return text
    out = text
    for token, original in mask_map.items():
        out = out.replace(token, original)
    return out
