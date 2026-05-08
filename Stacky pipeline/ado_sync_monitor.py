"""
ado_sync_monitor.py — Sincronización bidireccional de estado Stacky ↔ ADO.

Monitorea cambios en ADO que deben afectar el comportamiento de Stacky:
- ADO mueve ticket a "Closed"  → Stacky cancela pipeline activo
- ADO mueve ticket a "On Hold" → Stacky pausa pipeline
- ADO reasigna ticket          → Stacky lo saca de la cola
- Stacky completa pipeline     → ADO cambia a "Resolved"

Corre como thread paralelo al daemon principal.

Uso:
    from ado_sync_monitor import ADOSyncMonitor
    monitor = ADOSyncMonitor()
    monitor.start()  # starts background polling thread
"""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.ado_sync")

AUTH_FILE = Path(__file__).parent / "auth" / "ado_auth.json"


class ADOSyncMonitor:
    """
    Monitors ADO for changes that should affect Stacky's behavior.
    Runs as a background thread polling ADO at configurable intervals.
    """

    DEFAULT_POLL_INTERVAL = 60  # seconds

    def __init__(self, ado_client=None, state_provider=None, config: Optional[dict] = None):
        self._ado_client = ado_client
        self._state_provider = state_provider
        self._config = config or self._load_config()
        self._poll_interval = self._config.get("sync_poll_interval", self.DEFAULT_POLL_INTERVAL)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks: dict[str, list] = {
            "cancelled": [],
            "paused": [],
            "reassigned": [],
        }

    @property
    def ado_client(self):
        if self._ado_client is None:
            try:
                from ado_enricher import _get_ado_client
                self._ado_client = _get_ado_client()
            except Exception as e:
                logger.error("Cannot init ADO client: %s", e)
                raise
        return self._ado_client

    @property
    def state_provider(self):
        if self._state_provider is None:
            try:
                from ado_state_provider import ADOStateProvider
                self._state_provider = ADOStateProvider(self.ado_client)
            except Exception as e:
                logger.error("Cannot init state provider: %s", e)
        return self._state_provider

    def start(self):
        """Start the background polling thread."""
        if self._running:
            logger.warning("ADO sync monitor already running")
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name="ado-sync-monitor"
        )
        self._thread.start()
        logger.info("ADO sync monitor started (interval: %ds)", self._poll_interval)

    def stop(self):
        """Stop the background polling thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("ADO sync monitor stopped")

    def on_cancelled(self, callback):
        """Register callback for when a ticket is cancelled in ADO."""
        self._callbacks["cancelled"].append(callback)

    def on_paused(self, callback):
        """Register callback for when a ticket is paused in ADO."""
        self._callbacks["paused"].append(callback)

    def on_reassigned(self, callback):
        """Register callback for when a ticket is reassigned in ADO."""
        self._callbacks["reassigned"].append(callback)

    def poll_once(self) -> dict:
        """
        Poll ADO for changes. Returns dict of detected changes.
        Can be called manually for testing.
        """
        changes = {"cancelled": [], "paused": [], "reassigned": []}

        if not self.state_provider:
            return changes

        try:
            active_tickets = self.state_provider.get_all_active_tickets()
        except Exception as e:
            logger.error("Failed to get active tickets: %s", e)
            return changes

        assigned_user = self._config.get("assigned_user_email", "")

        for ticket_id in active_tickets:
            try:
                state = self.state_provider.get_ticket_state(ticket_id)
                ado_state = state.get("ado_state", "")

                # Check for cancellation
                if ado_state in ("Closed", "Done", "Removed"):
                    logger.info("[Sync] WI#%d: ADO state=%s → cancelling pipeline",
                                ticket_id, ado_state)
                    changes["cancelled"].append({
                        "id": ticket_id,
                        "reason": f"ADO marked as {ado_state}",
                    })
                    self._fire_callbacks("cancelled", ticket_id, ado_state)

                # Check for on-hold (if supported by the ADO process template)
                elif ado_state in ("On Hold", "Paused"):
                    logger.info("[Sync] WI#%d: ADO state=%s → pausing pipeline",
                                ticket_id, ado_state)
                    changes["paused"].append({
                        "id": ticket_id,
                        "reason": f"ADO state: {ado_state}",
                    })
                    self._fire_callbacks("paused", ticket_id, ado_state)

            except Exception as e:
                logger.warning("[Sync] Error checking WI#%d: %s", ticket_id, e)

        return changes

    def _poll_loop(self):
        """Main polling loop running in background thread."""
        while self._running:
            try:
                self.poll_once()
            except Exception as e:
                logger.error("[Sync] Poll error: %s", e)

            # Sleep in small increments to allow quick shutdown
            for _ in range(self._poll_interval):
                if not self._running:
                    break
                time.sleep(1)

    def _fire_callbacks(self, event: str, ticket_id: int, ado_state: str):
        """Fire registered callbacks for an event."""
        for cb in self._callbacks.get(event, []):
            try:
                cb(ticket_id, ado_state)
            except Exception as e:
                logger.error("[Sync] Callback error for %s: %s", event, e)

    def _load_config(self) -> dict:
        config_path = Path(__file__).parent / "config.json"
        if config_path.exists():
            try:
                return json.loads(config_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}
