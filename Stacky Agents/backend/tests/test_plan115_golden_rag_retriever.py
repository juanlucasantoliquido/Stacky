"""Plan 115 F0 — Golden byte-idéntico de rag_retriever (TF relativo, plan 64).

Captura la salida ACTUAL (antes del refactor). Debe seguir idéntica después de
migrar rag_retriever a lexical_core (F3). Scores redondeados a 6 decimales.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import rag_retriever as rr

_CHUNKS = [
    ("c1", "instalacion configuracion requisitos previos del sistema"),
    ("c2", "detalle procedimiento pasos finales verificacion"),
    ("c3", "configuracion avanzada del sistema y ajustes"),
]

# Golden capturado contra el código pre-refactor (2026-07-10).
_EXPECTED = [("c3", 0.556509), ("c1", 0.494265), ("c2", 0.0)]


def test_rag_retriever_golden():
    idx = rr.build_index([rr.RagChunk(id=i, text=t, payload={}) for i, t in _CHUNKS])
    res = rr.retrieve(idx, "configuracion sistema", top_k=3)
    got = [(c.id, round(s, 6)) for c, s in res]
    assert got == _EXPECTED
