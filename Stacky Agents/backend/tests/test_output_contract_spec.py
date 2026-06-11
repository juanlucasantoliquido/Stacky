"""H3.2 — Test de consistencia entre output-contract-v1.md y artifact_validator.

Parsea el markdown y verifica que:
  - Los campos listados en <!-- FIELDS_START --> / <!-- FIELDS_END --> coincidan
    exactamente con artifact_validator._required_fields() (fallback set).
  - Los estados listados en <!-- STATUSES_START --> / <!-- STATUSES_END --> coincidan
    exactamente con artifact_validator._allowed_statuses() (fallback set).

Si el doc diverge del validador, este test falla — no hay formas de que la
documentación quede desactualizada en silencio.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Ruta al spec (relativa a este archivo)
_SPEC_PATH = (
    Path(__file__).resolve().parents[3]
    / "Stacky Agents"
    / "docs"
    / "specs"
    / "output-contract-v1.md"
)


def _parse_block(text: str, tag: str) -> frozenset[str]:
    """Extrae los items de lista entre <!-- TAG_START --> y <!-- TAG_END -->."""
    pattern = rf"<!-- {tag}_START -->(.*?)<!-- {tag}_END -->"
    m = re.search(pattern, text, re.DOTALL)
    assert m, f"Bloque {tag} no encontrado en output-contract-v1.md"
    block = m.group(1)
    # Cada línea con formato "- `campo`" o "- campo"
    items: set[str] = set()
    for line in block.splitlines():
        line = line.strip()
        if line.startswith("- "):
            value = line[2:].strip().strip("`")
            if value:
                items.add(value)
    return frozenset(items)


def test_spec_exists():
    assert _SPEC_PATH.exists(), f"No encontré la spec en {_SPEC_PATH}"


def test_spec_required_fields_match_validator():
    """Campos del doc == _required_fields() del validador."""
    from services import artifact_validator as av

    spec_text = _SPEC_PATH.read_text(encoding="utf-8")
    doc_fields = _parse_block(spec_text, "FIELDS")
    code_fields = av._required_fields()

    missing_from_doc = code_fields - doc_fields
    extra_in_doc = doc_fields - code_fields

    assert not missing_from_doc, (
        f"Campos en el validador que faltan en el doc: {sorted(missing_from_doc)}"
    )
    assert not extra_in_doc, (
        f"Campos en el doc que no están en el validador: {sorted(extra_in_doc)}"
    )


def test_spec_allowed_statuses_match_validator():
    """Estados del doc == _allowed_statuses() del validador."""
    from services import artifact_validator as av

    spec_text = _SPEC_PATH.read_text(encoding="utf-8")
    doc_statuses = _parse_block(spec_text, "STATUSES")
    code_statuses = av._allowed_statuses()

    missing_from_doc = code_statuses - doc_statuses
    extra_in_doc = doc_statuses - code_statuses

    assert not missing_from_doc, (
        f"Estados en el validador que faltan en el doc: {sorted(missing_from_doc)}"
    )
    assert not extra_in_doc, (
        f"Estados en el doc que no están en el validador: {sorted(extra_in_doc)}"
    )
