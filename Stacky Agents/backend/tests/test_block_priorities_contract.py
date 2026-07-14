"""Plan 133 F6 — Prioridades de bloques honestas (cierra causa raíz 5)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_NEW_IDS = ["run-directive", "ado-blocker", "process-catalog", "process-discipline", "acceptance-contract"]


def test_bloques_obligatorios_sobre_umbral():
    from services.context_enrichment import _HIGH_PRIORITY_THRESHOLD, _block_priority

    for block_id in _NEW_IDS:
        assert _block_priority({"id": block_id}) >= _HIGH_PRIORITY_THRESHOLD, block_id


def test_priority_high_adhoc_respetada():
    from services.context_enrichment import _HIGH_PRIORITY_THRESHOLD, _block_priority

    assert _block_priority({"id": "cualquier-cosa", "priority": "high"}) == _HIGH_PRIORITY_THRESHOLD
    assert _block_priority({"id": "cualquier-cosa-2", "priority": "HIGH"}) == _HIGH_PRIORITY_THRESHOLD


def test_default_sin_cambios():
    from services.context_enrichment import _DEFAULT_PRIORITY, _block_priority

    assert _block_priority({"id": "desconocido"}) == _DEFAULT_PRIORITY


def test_budget_no_poda_process_catalog(monkeypatch):
    from config import config
    from services import cli_feature_flags, context_enrichment

    # Budget chico (200 tok ~ 800 chars): alcanza sobrado para el catálogo
    # (corto, alta prioridad, va primero) pero no para los comentarios (largos,
    # prioridad baja, van después) → el catálogo queda íntegro y los
    # comentarios se truncan.
    monkeypatch.setattr(config, "STACKY_CONTEXT_BUDGET_TOKENS", 200)
    monkeypatch.setattr(cli_feature_flags, "context_budget_enabled", lambda project=None: True)

    catalog_content = "catálogo de procesos obligatorio del proyecto"
    comments_content = "comentario viejo poco importante\n" * 200
    blocks = [
        {"id": "process-catalog", "content": catalog_content},
        {"id": "ado-comments", "content": comments_content},
    ]
    result = context_enrichment._apply_context_budget(
        blocks, project_name=None, log=lambda *a, **k: None, context_text=None,
    )
    result_by_id = {b["id"]: b for b in result}
    assert result_by_id["process-catalog"]["content"] == catalog_content
    assert len(result_by_id["ado-comments"]["content"]) < len(comments_content)
