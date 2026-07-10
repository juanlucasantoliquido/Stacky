"""Plan 115 F0 — Golden byte-idéntico del TF-IDF de memory_store.search (TF crudo).

Captura la salida ACTUAL (antes del refactor). Debe seguir idéntica después de
migrar memory_store a lexical_core (F4). Scores redondeados a 6 decimales.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db
from services import memory_store as ms

db.init_db()

_PROJECT = "G115_MEM"
_CORPUS = [
    ("t-a", "instalacion", "configuracion requisitos previos del sistema"),
    ("t-b", "detalle", "procedimiento pasos finales verificacion"),
    ("t-c", "config-avanzada", "configuracion avanzada del sistema y ajustes"),
]

# Golden capturado contra el código pre-refactor (2026-07-10).
_EXPECTED = [("t-a", 0.5275), ("t-c", 0.402)]


def _seed():
    for tk, title, content in _CORPUS:
        ms.upsert_by_topic_key(project=_PROJECT, type="decision", title=title,
                               content=content, topic_key=tk)


def test_memory_store_golden():
    _seed()
    hits = ms.search(project=_PROJECT, query_text="configuracion sistema", k=5)
    got = [(h.get("topic_key"), round(h.get("_score", 0.0), 6)) for h in hits]
    assert got == _EXPECTED
