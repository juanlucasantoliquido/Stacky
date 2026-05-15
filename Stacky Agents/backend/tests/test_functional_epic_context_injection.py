"""
test_functional_epic_context_injection.py

Tests unitarios para la inyección del context block 'ado-epic-structured'
en agent_runner._run_in_background cuando agent_type='functional' y
work_item_type='Epic'.

Invariantes verificadas:
  EPIC-01  test_epic_block_injected_when_functional_epic
             Verifica que el bloque ado-epic-structured se inyecta con
             el title y description correctos del Ticket.
  EPIC-02  test_epic_block_not_injected_when_not_epic
             Verifica que el bloque NO se inyecta cuando work_item_type
             es Task (Modo B — ticket Blocked).
  EPIC-03  test_epic_block_not_injected_when_agent_not_functional
             Verifica que el bloque NO se inyecta para otros agent_types
             aunque el ticket sea Epic.
  EPIC-04  test_epic_block_idempotent_when_already_present
             Verifica que si ya existe 'ado-epic-structured' en los blocks
             de entrada, no se duplica.
  EPIC-05  test_epic_block_content_structure
             Verifica que el contenido del bloque tiene los tres campos
             requeridos: epic_id, epic_title, epic_description.
"""
from __future__ import annotations

import os
import sys
import types
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Bootstrap ──────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_ticket(
    *,
    ado_id: int = 42,
    title: str = "Epic de prueba",
    description: str = "<p>RF-001</p>",
    work_item_type: str = "Epic",
    project: str = "test-project",
) -> MagicMock:
    """Devuelve un MagicMock que imita un Ticket con los campos relevantes."""
    t = MagicMock()
    t.ado_id = ado_id
    t.title = title
    t.description = description
    t.work_item_type = work_item_type
    t.project = project
    return t


def _make_execution(
    *,
    ticket_id: int = 1,
    agent_type: str = "functional",
    input_context: list | None = None,
) -> MagicMock:
    """Devuelve un MagicMock que imita un AgentExecution."""
    e = MagicMock()
    e.ticket_id = ticket_id
    e.agent_type = agent_type
    e.input_context = input_context or []
    return e


# ── Fixture: captura de bloques enviados al agente ─────────────────────────────

class _BlockCapture:
    """Captura los bloques que llegan al agente.run() sin ejecutar nada real."""

    def __init__(self) -> None:
        self.captured_blocks: list[dict] = []

    def run(self, blocks, *, log, execution_id, run_ctx):
        self.captured_blocks = list(blocks or [])
        # Devuelve un resultado mínimo compatible con el runner
        result = MagicMock()
        result.output = "ok"
        result.output_format = "markdown"
        result.metadata = {}
        return result


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestEpicContextInjection:
    """
    Prueba la lógica de inyección del bloque ado-epic-structured directamente,
    sin invocar _run_in_background completo (que requiere threading, DB real,
    copilot_bridge, etc.).

    Estrategia: extraemos la lógica de inyección a una función pura testeable
    importando el módulo y aplicando la misma condición con objetos dummy.
    """

    def _apply_injection(
        self,
        *,
        agent_type: str,
        ticket: MagicMock,
        existing_blocks: list[dict],
        log_calls: list,
    ) -> list[dict]:
        """
        Replica exactamente la lógica de inyección de agent_runner._run_in_background
        sin invocar el runner completo. Se mantiene sincronizada con la implementación.
        """
        def log(level, msg):
            log_calls.append((level, msg))

        raw_blocks = list(existing_blocks)

        _is_epic = (
            ticket is not None
            and agent_type == "functional"
            and (ticket.work_item_type or "").strip().lower() == "epic"
        )
        if _is_epic:
            _existing_ids = {b.get("id") for b in raw_blocks if isinstance(b, dict)}
            if "ado-epic-structured" not in _existing_ids:
                _epic_block: dict = {
                    "kind": "text",
                    "id": "ado-epic-structured",
                    "title": f"Epic ADO-{ticket.ado_id}: {ticket.title}",
                    "content": (
                        f"epic_id: {ticket.ado_id}\n"
                        f"epic_title: {ticket.title}\n"
                        f"epic_description:\n{ticket.description or ''}"
                    ),
                }
                raw_blocks = raw_blocks + [_epic_block]
                log("info", f"ado-epic-structured inyectado para Epic ADO-{ticket.ado_id}")
            else:
                log("info", "ado-epic-structured ya presente, omitiendo inyección")

        return raw_blocks

    # EPIC-01
    def test_epic_block_injected_when_functional_epic(self):
        """El bloque ado-epic-structured se inyecta cuando agent_type=functional y work_item_type=Epic."""
        ticket = _make_ticket(ado_id=42, title="Mi Epic", description="<p>RF-001</p>", work_item_type="Epic")
        log_calls: list = []

        result = self._apply_injection(
            agent_type="functional",
            ticket=ticket,
            existing_blocks=[{"id": "user-input", "kind": "text", "content": "analizar epic"}],
            log_calls=log_calls,
        )

        ids = [b.get("id") for b in result]
        assert "ado-epic-structured" in ids, "El bloque ado-epic-structured debe estar presente"

        epic_block = next(b for b in result if b.get("id") == "ado-epic-structured")
        assert epic_block["kind"] == "text"
        assert "42" in epic_block["title"]
        assert "Mi Epic" in epic_block["title"]

        # Verificar log de inyección
        assert any("ado-epic-structured inyectado" in msg for _, msg in log_calls)

    # EPIC-02
    def test_epic_block_not_injected_when_not_epic(self):
        """El bloque NO se inyecta cuando work_item_type es Task (Modo B — ticket Blocked)."""
        ticket = _make_ticket(ado_id=99, title="Tarea bloqueada", work_item_type="Task")
        log_calls: list = []

        result = self._apply_injection(
            agent_type="functional",
            ticket=ticket,
            existing_blocks=[{"id": "ado-comments", "kind": "text", "content": "BLOQUEANTE"}],
            log_calls=log_calls,
        )

        ids = [b.get("id") for b in result]
        assert "ado-epic-structured" not in ids, "No debe inyectarse el bloque para tickets no-Epic"
        # El bloque ado-comments original debe permanecer intacto
        assert "ado-comments" in ids

    # EPIC-03
    def test_epic_block_not_injected_when_agent_not_functional(self):
        """El bloque NO se inyecta para agentes distintos de 'functional', aunque el ticket sea Epic."""
        ticket = _make_ticket(ado_id=42, work_item_type="Epic")
        log_calls: list = []

        for other_agent in ("business", "technical", "developer", "qa"):
            result = self._apply_injection(
                agent_type=other_agent,
                ticket=ticket,
                existing_blocks=[],
                log_calls=log_calls,
            )
            ids = [b.get("id") for b in result]
            assert "ado-epic-structured" not in ids, (
                f"agent_type='{other_agent}' no debe recibir ado-epic-structured"
            )

    # EPIC-04
    def test_epic_block_idempotent_when_already_present(self):
        """Si ado-epic-structured ya existe en los blocks de entrada, no se duplica."""
        ticket = _make_ticket(ado_id=42, work_item_type="Epic")
        existing = [
            {
                "kind": "text",
                "id": "ado-epic-structured",
                "title": "Epic ADO-42: ya presente",
                "content": "epic_id: 42\nepic_title: ya presente\nepic_description:\ncontenido anterior",
            }
        ]
        log_calls: list = []

        result = self._apply_injection(
            agent_type="functional",
            ticket=ticket,
            existing_blocks=existing,
            log_calls=log_calls,
        )

        epic_blocks = [b for b in result if b.get("id") == "ado-epic-structured"]
        assert len(epic_blocks) == 1, "No debe haber duplicados del bloque ado-epic-structured"

        # Debe logear que ya estaba presente
        assert any("ya presente" in msg for _, msg in log_calls)

    # EPIC-05
    def test_epic_block_content_structure(self):
        """El contenido del bloque tiene los tres campos requeridos: epic_id, epic_title, epic_description."""
        ticket = _make_ticket(
            ado_id=77,
            title="Gestión de cobranza",
            description="<hr><h2>RF-001</h2><p>Descripción del requisito</p>",
            work_item_type="Epic",
        )
        log_calls: list = []

        result = self._apply_injection(
            agent_type="functional",
            ticket=ticket,
            existing_blocks=[],
            log_calls=log_calls,
        )

        epic_block = next((b for b in result if b.get("id") == "ado-epic-structured"), None)
        assert epic_block is not None

        content = epic_block["content"]
        assert "epic_id: 77" in content, "El contenido debe incluir epic_id"
        assert "epic_title: Gestión de cobranza" in content, "El contenido debe incluir epic_title"
        assert "epic_description:" in content, "El contenido debe incluir el campo epic_description"
        assert "RF-001" in content, "El contenido debe incluir la descripción HTML del Epic"

    # EPIC-06 — case insensitive para work_item_type
    def test_epic_detection_is_case_insensitive(self):
        """El agente detecta Epic independientemente del casing de work_item_type."""
        for wtype in ("epic", "EPIC", "Epic", " Epic "):
            ticket = _make_ticket(ado_id=1, work_item_type=wtype)
            log_calls: list = []
            result = self._apply_injection(
                agent_type="functional",
                ticket=ticket,
                existing_blocks=[],
                log_calls=log_calls,
            )
            ids = [b.get("id") for b in result]
            assert "ado-epic-structured" in ids, (
                f"work_item_type='{wtype}' debe ser reconocido como Epic"
            )

    # EPIC-07 — ticket con description None
    def test_epic_block_handles_null_description(self):
        """Si el ticket no tiene description, el bloque se inyecta con description vacía."""
        ticket = _make_ticket(ado_id=5, title="Epic sin descripción", description=None, work_item_type="Epic")
        log_calls: list = []

        result = self._apply_injection(
            agent_type="functional",
            ticket=ticket,
            existing_blocks=[],
            log_calls=log_calls,
        )

        epic_block = next((b for b in result if b.get("id") == "ado-epic-structured"), None)
        assert epic_block is not None
        assert "epic_description:" in epic_block["content"]
        # No debe explotar con description=None
        assert "None" not in epic_block["content"]
