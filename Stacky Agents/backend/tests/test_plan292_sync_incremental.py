"""tests/test_plan292_sync_incremental.py — Plan 292 F1 (+ F5).

El sync de GitLab deja de preguntar todo cada vez. Este archivo es el gate de
CORRECTITUD del plan, y tiene DOS invariantes centrales, no uno:

- LECTURA: en modo parcial la regla de ausencia (gitlab_sync.py:310-326) se apaga
  POR COMPLETO. Con un delta PARCIAL NO VACIO —no vacio: con la tanda vacia el
  `if vistos_external:` preexistente ya corta y el gate no discrimina— el sync no
  puede marcar `closed` ni una fila.
- ESCRITURA: en modo parcial la query es `state="all"`, asi que llegan CERRADOS.
  Un cerrado que no tiene fila local NO puede crear una: nadie la borraria nunca,
  `list_tickets` no filtra por estado y la fila fantasma se comeria una de las 500
  posiciones del tablero.

F1 crea el archivo con los 3 casos del carril (`TrackerQuery.updated_after`);
F5 lo completa con los casos 4..21.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ───────────────────────── F1 — el carril ─────────────────────────


def test_trackerquery_acepta_updated_after_y_su_default_es_none():
    from services.tracker_provider import TrackerQuery

    assert TrackerQuery().updated_after is None
    q = TrackerQuery(updated_after="2026-01-01T00:00:00Z")
    assert q.updated_after == "2026-01-01T00:00:00Z"


def _params(query):
    from services.gitlab_provider import GitLabTrackerProvider

    # `_query_to_gitlab_params` no toca `self`: se invoca sin construir el
    # proveedor, que exigiria configuracion del operador.
    return GitLabTrackerProvider._query_to_gitlab_params(None, query)


def test_query_sin_updated_after_no_emite_el_parametro():
    from services.tracker_provider import TrackerQuery

    params = _params(TrackerQuery(state="open"))
    assert params == {"state": "opened"}
    assert "updated_after" not in params


def test_query_con_updated_after_lo_emite_tal_cual():
    from services.tracker_provider import TrackerQuery

    params = _params(TrackerQuery(state="all", updated_after="2026-08-01T10:00:00Z"))
    assert params["updated_after"] == "2026-08-01T10:00:00Z"
    # `state="all"` NO emite el parametro `state`: GitLab sin `state` devuelve
    # todos, que es exactamente lo que el modo parcial necesita.
    assert "state" not in params
