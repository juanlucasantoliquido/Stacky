"""
ado_state_provider.py — Almacena el estado del pipeline Stacky en campos del Work Item ADO.

Elimina la dependencia de state/seen_tickets.json como única fuente de verdad.
Los campos usados son tags con prefijo "stacky:" y campos custom si están configurados.

Uso:
    from ado_state_provider import ADOStateProvider
    provider = ADOStateProvider()
    state = provider.get_ticket_state(27698)
    provider.set_ticket_state(27698, "pm_completado", "dev_en_proceso")
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.ado_state")

# Auth config
_AUTH_FILE = Path(__file__).parent / "auth" / "ado_auth.json"

# Tag prefix managed by Stacky
STACKY_TAG_PREFIX = "stacky:"

# Known Stacky states
VALID_STATES = {
    "pendiente", "pm_en_proceso", "pm_completado",
    "dev_en_proceso", "dev_completado",
    "qa_en_proceso", "qa_completado",
    "completado", "error", "bloqueado", "qa_rework",
}

# Known Stacky stages
VALID_STAGES = {
    "pm", "dev", "tester", "rework_dev", "rework_qa",
    "completado", "error",
}


def _load_auth() -> dict:
    """Load ADO authentication configuration."""
    if not _AUTH_FILE.exists():
        logger.warning("ADO auth file not found: %s", _AUTH_FILE)
        return {}
    return json.loads(_AUTH_FILE.read_text(encoding="utf-8"))


class ADOStateProvider:
    """
    Almacena el estado del pipeline Stacky en tags del Work Item ADO.
    Usa tags con prefijo 'stacky:' para state y stage tracking.
    """

    def __init__(self, ado_client=None):
        self._ado_client = ado_client
        self._auth = _load_auth()

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

    def get_ticket_state(self, work_item_id: int) -> dict:
        """Lee estado Stacky desde tags del Work Item."""
        try:
            wi = self.ado_client.get_work_item(work_item_id)
            fields = wi.get("fields", {})
            tags_str = fields.get("System.Tags", "")
            tags = [t.strip() for t in tags_str.split(";") if t.strip()]
            stacky_tags = [t for t in tags if t.startswith(STACKY_TAG_PREFIX)]

            stacky_state = None
            stacky_stage = None
            rework_cycles = 0
            processed_at = None

            for tag in stacky_tags:
                value = tag[len(STACKY_TAG_PREFIX):]
                if value.startswith("state_"):
                    stacky_state = value[len("state_"):]
                elif value.startswith("stage_"):
                    stacky_stage = value[len("stage_"):]
                elif value.startswith("rework_"):
                    try:
                        rework_cycles = int(value[len("rework_"):])
                    except ValueError:
                        pass
                elif value.startswith("processed_"):
                    processed_at = value[len("processed_"):]

            return {
                "ado_state": fields.get("System.State"),
                "ado_title": fields.get("System.Title"),
                "stacky_state": stacky_state,
                "stacky_stage": stacky_stage,
                "rework_cycles": rework_cycles,
                "processed_at": processed_at,
                "stacky_tags": stacky_tags,
                "all_tags": tags,
            }
        except Exception as e:
            logger.error("Failed to get state for WI#%d: %s", work_item_id, e)
            return {
                "ado_state": None,
                "stacky_state": None,
                "stacky_stage": None,
                "rework_cycles": 0,
                "processed_at": None,
                "stacky_tags": [],
                "all_tags": [],
            }

    def set_ticket_state(
        self,
        work_item_id: int,
        stacky_state: str,
        stacky_stage: str,
        rework_cycles: int = 0,
    ):
        """Actualiza tags Stacky del Work Item con el estado actual del pipeline."""
        if stacky_state not in VALID_STATES:
            logger.warning("Invalid stacky_state: %s", stacky_state)

        try:
            current = self.get_ticket_state(work_item_id)
            all_tags = current.get("all_tags", [])

            # Remove old stacky tags
            non_stacky = [t for t in all_tags if not t.startswith(STACKY_TAG_PREFIX)]

            # Build new stacky tags
            new_stacky = [
                f"{STACKY_TAG_PREFIX}state_{stacky_state}",
                f"{STACKY_TAG_PREFIX}stage_{stacky_stage}",
                f"{STACKY_TAG_PREFIX}rework_{rework_cycles}",
                f"{STACKY_TAG_PREFIX}processed_{datetime.now().strftime('%Y%m%d_%H%M')}",
            ]

            updated_tags = non_stacky + new_stacky
            tags_str = "; ".join(updated_tags)

            self.ado_client.update_work_item(work_item_id, {
                "System.Tags": tags_str,
            })
            logger.info(
                "ADO WI#%d state updated: %s / %s (rework: %d)",
                work_item_id, stacky_state, stacky_stage, rework_cycles,
            )
        except Exception as e:
            logger.error("Failed to set state for WI#%d: %s", work_item_id, e)

    def clear_stacky_tags(self, work_item_id: int):
        """Remove all stacky: tags from a Work Item."""
        try:
            current = self.get_ticket_state(work_item_id)
            non_stacky = [t for t in current.get("all_tags", [])
                          if not t.startswith(STACKY_TAG_PREFIX)]
            tags_str = "; ".join(non_stacky)
            self.ado_client.update_work_item(work_item_id, {
                "System.Tags": tags_str,
            })
            logger.info("ADO WI#%d: all stacky tags cleared", work_item_id)
        except Exception as e:
            logger.error("Failed to clear tags for WI#%d: %s", work_item_id, e)

    def get_all_active_tickets(self) -> list[int]:
        """Get all Work Items with stacky:state_ tags that indicate active processing."""
        try:
            wiql = (
                "SELECT [System.Id] FROM WorkItems "
                "WHERE [System.Tags] CONTAINS 'stacky:state_' "
                "AND [System.Tags] NOT CONTAINS 'stacky:state_completado' "
                "AND [System.Tags] NOT CONTAINS 'stacky:state_error' "
                "ORDER BY [System.ChangedDate] DESC"
            )
            results = self.ado_client.query_wiql(wiql)
            return [wi["id"] for wi in results.get("workItems", [])]
        except Exception as e:
            logger.error("Failed to query active tickets: %s", e)
            return []

    def is_already_processed(self, work_item_id: int) -> bool:
        """Check if a Work Item was already processed by Stacky."""
        state = self.get_ticket_state(work_item_id)
        return state.get("stacky_state") in ("completado", "error")
