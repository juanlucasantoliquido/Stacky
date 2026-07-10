"""Plan 115 F5 [ADICIÓN ARQUITECTO] — meta-test: la matemática TF-IDF vive SOLO en
lexical_core. Automatiza lo que v1 dejaba como "lectura manual del diff"."""
from __future__ import annotations

import re
from pathlib import Path

_SERVICES = Path(__file__).resolve().parents[1] / "services"
_CONSUMERS = ["rag_retriever.py", "docs_rag.py", "memory_store.py"]


def _read(name: str) -> str:
    return (_SERVICES / name).read_text(encoding="utf-8")


def test_consumers_import_lexical_core():
    for name in _CONSUMERS:
        src = _read(name)
        assert ("from services import lexical_core" in src
                or "from services.lexical_core import" in src), name


def test_consumers_have_no_own_idf_math():
    for name in _CONSUMERS:
        assert re.search(r"math\.log\(", _read(name)) is None, (
            f"{name} todavía calcula IDF por su cuenta (math.log)")


def test_lexical_core_owns_the_idf_math():
    assert re.search(r"math\.log\(", _read("lexical_core.py")) is not None
