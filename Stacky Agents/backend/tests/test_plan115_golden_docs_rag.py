"""Plan 115 F0 — Golden byte-idéntico de docs_rag.search (TF crudo + cache IDF).

Captura la salida ACTUAL (antes del refactor). Debe seguir idéntica después de
migrar docs_rag a lexical_core (F2). Scores redondeados a 6 decimales.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db
from services import docs_rag

db.init_db()

_PROJECT = "G115_DOCS"
_CORPUS = [
    ("a.md", "instalacion configuracion requisitos previos del sistema"),
    ("b.md", "detalle procedimiento pasos finales verificacion"),
    ("c.md", "configuracion avanzada del sistema y ajustes generales"),
]

# Golden capturado contra el código pre-refactor (2026-07-10).
_EXPECTED = [("a.md", 0.527533), ("c.md", 0.527533)]


def _seed():
    with db.session_scope() as s:
        s.query(docs_rag.DocChunk).filter_by(project_name=_PROJECT).delete()
    docs_rag._invalidate_idf(_PROJECT)
    for fp, text in _CORPUS:
        tf, norm = docs_rag._compute_tf(text)
        with db.session_scope() as s:
            s.add(docs_rag.DocChunk(
                project_name=_PROJECT, file_path=fp, section_heading="",
                chunk_text=text, term_freqs_json=docs_rag.json.dumps(dict(tf)),
                doc_norm=norm))


def test_docs_rag_golden():
    _seed()
    hits = docs_rag.search(_PROJECT, "configuracion sistema", top_k=5, expand_files=False)
    got = [(h.file_path, round(h.score, 6)) for h in hits]
    assert got == _EXPECTED
