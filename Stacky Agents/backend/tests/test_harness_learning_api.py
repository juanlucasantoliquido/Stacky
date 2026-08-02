"""Plan 35 F4 — visibilidad de patrones para el operador (lectura + confirmar/descartar).

Numeración POR ARCHIVO: A1..A5.

Comando:
  & "…/backend/venv/Scripts/python.exe" -m pytest "tests/test_harness_learning_api.py" -q
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="module")
def client():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def _seed(project, *, signal_key, veces=1, agent_type="developer", ticket_kind="bug"):
    from services.harness_learning import HarnessPattern, persist_pattern

    p = HarnessPattern(
        project=project, agent_type=agent_type, ticket_kind=ticket_kind,
        signal_kind="criterion_fail", signal_key=signal_key, remedy_hint="",
        occurrences=1, confidence=0.0, last_seen="2026-08-01",
    )
    mid = ""
    for _ in range(veces):
        mid = persist_pattern(p)
    return mid


def test_list_endpoint_returns_patterns_sorted(client):
    """A1 — la lista viene ordenada por confianza descendente."""
    proj = "HLA_LIST"
    _seed(proj, signal_key="poco frecuente", veces=1)
    _seed(proj, signal_key="muy frecuente", veces=5)
    _seed(proj, signal_key="frecuencia media", veces=3)

    r = client.get(f"/api/diag/harness-patterns?project={proj}")
    assert r.status_code == 200
    data = r.get_json()
    items = data["patterns"]
    assert len(items) == 3
    confs = [i["confidence"] for i in items]
    assert confs == sorted(confs, reverse=True), f"sin ordenar: {confs}"
    assert "muy frecuente" in items[0]["signal_key"]
    assert all(i.get("id") for i in items), "cada patrón debe traer su memory id"

    # proyecto sin patrones: lista vacía, no error
    r2 = client.get("/api/diag/harness-patterns?project=HLA_NADA")
    assert r2.status_code == 200 and r2.get_json()["patterns"] == []


def test_dismiss_sets_status_rejected(client):
    """A2 — descartar pasa a "rejected" y lo saca de list_patterns."""
    from services import memory_store
    from services.harness_learning import PATTERN_STATUS_DISMISSED, list_patterns

    proj = "HLA_DISM"
    mid = _seed(proj, signal_key="senal a descartar", veces=3)
    assert list_patterns(proj, min_confidence=0.0)

    r = client.post(f"/api/diag/harness-patterns/{mid}/dismiss")
    assert r.status_code == 200
    assert memory_store.get(mid)["status"] == PATTERN_STATUS_DISMISSED
    assert list_patterns(proj, min_confidence=0.0) == []


def test_confirm_reactivates_pattern(client):
    """A3 — el operador puede revertir SU PROPIO descarte.

    No contradice el descarte de por vida: lo que la decisión (b) prohíbe es que
    la COSECHA AUTOMÁTICA lo resucite, no que el operador cambie de opinión.
    """
    from services import memory_store
    from services.harness_learning import PATTERN_STATUS_ACTIVE, list_patterns

    proj = "HLA_CONF"
    mid = _seed(proj, signal_key="senal a reactivar", veces=3)
    client.post(f"/api/diag/harness-patterns/{mid}/dismiss")
    assert list_patterns(proj, min_confidence=0.0) == []

    r = client.post(f"/api/diag/harness-patterns/{mid}/confirm")
    assert r.status_code == 200
    assert memory_store.get(mid)["status"] == PATTERN_STATUS_ACTIVE
    assert list_patterns(proj, min_confidence=0.0), "confirm no lo devolvió a la lista"


def test_dismiss_unknown_id_returns_404(client):
    """A4 — id inexistente → 404 (set_status devuelve False)."""
    assert client.post("/api/diag/harness-patterns/mem-no-existe/dismiss").status_code == 404
    assert client.post("/api/diag/harness-patterns/mem-no-existe/confirm").status_code == 404


def test_endpoints_never_mutate_tickets_or_publish(client, monkeypatch):
    """A5 — GATE de la regla 11: ninguna acción publica ni transiciona work items."""
    import services.ticket_status as ts

    proj = "HLA_R11"
    mid = _seed(proj, signal_key="senal inocua", veces=3)

    llamadas = []
    monkeypatch.setattr(
        ts, "set_status",
        lambda *a, **k: llamadas.append(("ticket_status.set_status", a, k)),
    )
    monkeypatch.setattr(
        ts, "on_execution_end",
        lambda *a, **k: llamadas.append(("on_execution_end", a, k)),
    )

    # …y ningún publisher del tracker se toca
    for modname, attr in (
        ("services.epic_autopublish", "maybe_autopublish_epic"),
        ("services.incident_autopublish", "maybe_autopublish_incident"),
    ):
        import importlib

        mod = importlib.import_module(modname)
        monkeypatch.setattr(
            mod, attr, lambda *a, **k: llamadas.append((f"{modname}.{attr}", a, k))
        )

    assert client.get(f"/api/diag/harness-patterns?project={proj}").status_code == 200
    assert client.post(f"/api/diag/harness-patterns/{mid}/dismiss").status_code == 200
    assert client.post(f"/api/diag/harness-patterns/{mid}/confirm").status_code == 200

    assert llamadas == [], f"los endpoints tocaron el tracker o el ticket: {llamadas}"

    # guarda POSITIVA: el spy SÍ registra cuando algo llama de verdad
    ts.set_status(1, "completed")
    assert llamadas, "el spy no funciona: A5 no probaría nada"
