"""
auto_escalator.py — ADO Blocker Auto-Escalation.

Cuando el pipeline queda bloqueado (3+ reintentos fallidos), crea automáticamente
un Bug en ADO vinculado al ticket original y lo asigna al TL para intervención manual.

Uso:
    from auto_escalator import AutoEscalator
    escalator = AutoEscalator(config)
    escalator.escalate_blocked_ticket(ticket_id, work_item_id, reason, retries)
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.auto_escalator")


class AutoEscalator:
    """Automatically escalates blocked pipeline tickets to ADO."""

    ESCALATION_THRESHOLD = 3  # retries before escalating

    def __init__(self, ado_client=None, config: Optional[dict] = None):
        self._ado_client = ado_client
        self.config = config or self._load_config()

    @property
    def ado_client(self):
        if self._ado_client is None:
            try:
                from ado_enricher import _get_ado_client
                self._ado_client = _get_ado_client()
            except Exception as e:
                logger.error("Cannot initialize ADO client: %s", e)
                raise
        return self._ado_client

    def _load_config(self) -> dict:
        config_path = Path(__file__).parent / "config.json"
        if config_path.exists():
            return json.loads(config_path.read_text(encoding="utf-8"))
        return {}

    def should_escalate(self, retries: int) -> bool:
        """Check if the number of retries warrants escalation."""
        return retries >= self.ESCALATION_THRESHOLD

    def escalate_blocked_ticket(
        self,
        ticket_id: str,
        work_item_id: int,
        reason: str,
        retries: int,
    ) -> Optional[int]:
        """
        Escalate a blocked ticket by creating a Bug in ADO linked to the original.

        Returns the created Bug's Work Item ID, or None if not escalated.
        """
        if retries < self.ESCALATION_THRESHOLD:
            logger.debug("Not escalating WI#%d: %d retries < threshold %d",
                         work_item_id, retries, self.ESCALATION_THRESHOLD)
            return None

        logger.warning(
            "ESCALATING WI#%d (ticket %s): %d retries, reason: %s",
            work_item_id, ticket_id, retries, reason
        )

        try:
            # Create Bug in ADO
            bug_title = (
                f"[Stacky Auto-Escalation] Pipeline bloqueado — "
                f"Ticket #{work_item_id}"
            )
            bug_description = (
                f"<h3>Pipeline bloqueado después de {retries} reintentos</h3>"
                f"<p><b>Razón:</b> {self._sanitize_html(reason)}</p>"
                f"<p><b>Ticket original:</b> #{work_item_id}</p>"
                f"<p><b>Ticket local ID:</b> {ticket_id}</p>"
                f"<p><b>Timestamp:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>"
                f"<p><b>Acción requerida:</b> Revisar dashboard Stacky o ejecutar "
                f"retry manual.</p>"
            )

            assignee = self.config.get("escalation_assignee", "")

            bug_id = self.ado_client.create_work_item(
                type="Bug",
                title=bug_title,
                description=bug_description,
                assigned_to=assignee if assignee else None,
                tags="stacky:escalation; stacky:blocked",
            )

            bug_id_val = bug_id if isinstance(bug_id, int) else bug_id.get("id")

            # Link Bug to original Work Item
            if bug_id_val:
                try:
                    self.ado_client.link_work_items(
                        work_item_id, bug_id_val, "Related"
                    )
                except Exception as e:
                    logger.warning("Failed to link bug #%s to WI#%d: %s",
                                   bug_id_val, work_item_id, e)

                # Add comment to original Work Item
                try:
                    self.ado_client.add_comment(
                        work_item_id,
                        f"⚠️ **STACKY AUTO-ESCALATION**: Pipeline bloqueado "
                        f"({retries} reintentos). Bug creado: #{bug_id_val}. "
                        f"Intervención manual requerida."
                    )
                except Exception as e:
                    logger.warning("Failed to add escalation comment: %s", e)

            logger.info("Escalation bug created: #%s for WI#%d", bug_id_val, work_item_id)
            return bug_id_val

        except Exception as e:
            logger.error("Failed to create escalation bug for WI#%d: %s",
                         work_item_id, e)
            return None

    def _sanitize_html(self, text: str) -> str:
        """Basic HTML sanitization for ADO description."""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
