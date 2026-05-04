"""
action_log — Middleware de persistencia de acciones mutativas con rollback.

Cada acción mutativa (ADO, RIDIOMA, archivo) queda registrada en un log
JSON-lines con su reverse-action ejecutable. Habilita rollback determinístico.

Uso:
    from action_log import log_action, reverse_action, list_actions
    from action_log.logger import ActionLogEntry
"""
from .logger import log_action, list_actions, get_action, ActionLogEntry
from .reverser import reverse_action

__all__ = [
    "log_action",
    "list_actions",
    "get_action",
    "reverse_action",
    "ActionLogEntry",
]
