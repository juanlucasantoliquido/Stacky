"""
notification_event_tester.py — Notification & Event Trigger Test.

Verifies that batch processing generates expected notifications, events,
and sync flags.

Uso:
    from notification_event_tester import NotificationEventTester
    tester = NotificationEventTester(config)
    cases = tester.verify(ticket_folder, config)
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.notification_event")


@dataclass
class ExpectedEvent:
    name: str
    table: str
    type: str = "event"  # "event", "email", "flag"


@dataclass
class NotifTestCase:
    event_type: str
    expected_count: int = 0
    actual_count: int = 0
    passed: bool = False


class NotificationEventTester:
    def __init__(self, config: Optional[dict] = None,
                 batch_executor=None, mock_generator=None, db=None):
        self.config = config or {}
        self.batch_executor = batch_executor
        self.mock_generator = mock_generator
        self.db = db

    def verify(self, ticket_folder: str, config: Optional[dict] = None) -> list[NotifTestCase]:
        if not self.batch_executor or not self.db:
            return []

        events = self._extract_expected_events(ticket_folder)
        if not events:
            return []

        # Generate and insert mock data
        mock_count = 3
        if self.mock_generator:
            mock = self.mock_generator.generate(rows=mock_count)
            self.db.insert(mock)

        # Capture state BEFORE
        event_counts_before = {}
        for ev in events:
            try:
                event_counts_before[ev.table] = self._get_count(ev.table)
            except Exception:
                event_counts_before[ev.table] = 0

        # Execute batch
        self.batch_executor.run_minimal(ticket_folder)

        # Verify events generated
        cases = []
        for ev in events:
            try:
                after_count = self._get_count(ev.table)
                new_events = after_count - event_counts_before.get(ev.table, 0)

                cases.append(NotifTestCase(
                    event_type=ev.name,
                    expected_count=mock_count,
                    actual_count=new_events,
                    passed=(new_events >= 1),
                ))

                # If email table: verify recipient exists
                if ev.type == "email" and new_events > 0:
                    has_recipient = self._check_email_recipient(ev.table)
                    cases.append(NotifTestCase(
                        event_type=f"{ev.name} recipient",
                        expected_count=1,
                        actual_count=1 if has_recipient else 0,
                        passed=has_recipient,
                    ))

            except Exception as e:
                cases.append(NotifTestCase(
                    event_type=ev.name,
                    passed=False,
                ))
                logger.error("[NotifEvent] Error checking %s: %s", ev.name, e)

        return cases

    def _extract_expected_events(self, ticket_folder: str) -> list[ExpectedEvent]:
        folder = Path(ticket_folder)
        events = []
        for fname in ["TAREAS_DESARROLLO.md", "ARQUITECTURA_SOLUCION.md"]:
            p = folder / fname
            if not p.exists():
                continue
            content = p.read_text(encoding="utf-8", errors="replace").lower()

            if any(k in content for k in ["email", "correo", "notificación"]):
                events.append(ExpectedEvent(
                    name="Email notification",
                    table="REMAIL_QUEUE",
                    type="email"
                ))
            if any(k in content for k in ["evento", "event", "log"]):
                events.append(ExpectedEvent(
                    name="Event log",
                    table="REVENTOS",
                    type="event"
                ))
            if any(k in content for k in ["sync", "sincronización", "flag"]):
                events.append(ExpectedEvent(
                    name="Sync flag",
                    table="RSYNC_FLAGS",
                    type="flag"
                ))

        return events

    def _get_count(self, table: str) -> int:
        if hasattr(self.db, "count"):
            return self.db.count(table)
        cursor = self.db.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        return cursor.fetchone()[0]

    def _check_email_recipient(self, table: str) -> bool:
        try:
            cursor = self.db.cursor()
            cursor.execute(
                f"SELECT TOP 1 RDESTINATARIO FROM {table} "
                f"ORDER BY RFEC_ENVIO DESC"
            )
            row = cursor.fetchone()
            return row is not None and row[0] is not None
        except Exception:
            return False
