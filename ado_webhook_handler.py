"""
ado_webhook_handler.py — ADO Webhook → trigger automático de Stacky.

Receives ADO Service Hook webhooks for work item state changes and queues tickets
for pipeline processing.

Uso:
    # Register routes in dashboard_server.py:
    from ado_webhook_handler import ADOWebhookHandler
    handler = ADOWebhookHandler(daemon, config)
    app.add_url_rule("/api/v1/webhooks/ado_state_change", view_func=handler.handle, methods=["POST"])
"""

import hashlib
import hmac
import json
import logging
from typing import Optional

logger = logging.getLogger("stacky.webhook")


class ADOWebhookHandler:
    def __init__(self, daemon=None, config: Optional[dict] = None):
        self._daemon = daemon
        self._config = config or {}
        self._webhook_secret = self._config.get("webhook_secret", "")
        self._assigned_user = self._config.get("assigned_user_email", "")

    def handle(self, request_data: bytes, request_headers: dict) -> dict:
        """
        Process an ADO webhook request.

        Args:
            request_data: Raw request body bytes
            request_headers: Dict of request headers

        Returns:
            dict with status and optional data
        """
        # Verify signature if secret configured
        if self._webhook_secret:
            signature = request_headers.get("X-VSTS-Signature", "")
            if not self._verify_signature(signature, request_data):
                logger.warning("[Webhook] Invalid signature — rejecting request")
                return {"error": "Invalid signature", "status": 401}

        try:
            payload = json.loads(request_data)
        except (json.JSONDecodeError, ValueError):
            return {"error": "Invalid JSON", "status": 400}

        event_type = payload.get("eventType", "")
        if event_type != "workitem.updated":
            return {"ignored": True, "reason": f"Unsupported event: {event_type}", "status": 200}

        resource = payload.get("resource", {})
        wi_id = resource.get("id")
        if not wi_id:
            return {"error": "No work item ID", "status": 400}

        fields = resource.get("fields", {})
        new_state = fields.get("System.State", {}).get("newValue", "")
        assigned_to = fields.get("System.AssignedTo", {}).get("newValue", {})
        assigned_email = assigned_to.get("uniqueName", "") if isinstance(assigned_to, dict) else ""

        # Only process if state changed to Active and assigned to our user
        if new_state == "Active":
            if not self._assigned_user or assigned_email == self._assigned_user:
                if self._daemon and hasattr(self._daemon, "queue_ticket"):
                    self._daemon.queue_ticket(str(wi_id), priority="webhook")
                    logger.info("[Webhook] Queued WI#%s (webhook priority)", wi_id)
                    return {"queued": wi_id, "status": 202}
                else:
                    logger.warning("[Webhook] No daemon to queue WI#%s", wi_id)
                    return {"error": "Daemon not connected", "status": 503}

        return {"ignored": True, "reason": "State not Active or not assigned", "status": 200}

    def _verify_signature(self, signature: str, body: bytes) -> bool:
        if not self._webhook_secret:
            return True
        expected = hmac.new(
            self._webhook_secret.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, expected)
