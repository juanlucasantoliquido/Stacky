"""stacky_ado_bridge.py — Puente SOLO-LECTURA al cliente ADO de Stacky (Plan 240 F5).

Por que existe (H6): uat_ticket_reader invoca `Stacky tools/ADO Manager/ado.py`, que
resuelve el PAT solo desde ado-config.json / PAT-ADO EN TEXTO PLANO y ninguno existe
=> el pipeline moria en el stage reader con BLOCKED/PIP/ado_error. Stacky ya tiene el
PAT cifrado con DPAPI en backend/projects/<proyecto>/auth/ado_auth.json y funciona.

ALCANCE DURO: SOLO LECTURA. Este modulo no expone NINGUN metodo de escritura de
AdoClient — ni creacion de work items, ni publicacion de comentarios, ni cambio de
estados, ni subida de adjuntos. El HITL de publicacion queda intacto.

(C11) El docstring evita a proposito escribir los nombres literales de los metodos de
escritura: el criterio de aceptacion de esta fase es un grep de esos literales con
resultado 0, y nombrarlos aqui haria fallar el gate contra su propio autor.

(C16) Verificado: services/ado_client.py importa solo `config` y
`services.secrets_store` — no importa db ni models, asi que este sys.path insert es
liviano y no levanta engine de BD (seguro tambien desde la CLI).
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger("stacky.qa_uat.ado_bridge")

_TOOL_ROOT = Path(__file__).resolve().parent
# tool = <repo>/Stacky tools/QA UAT Agent  =>  backend = <repo>/Stacky Agents/backend
_BACKEND = _TOOL_ROOT.parent.parent / "Stacky Agents" / "backend"

_READ_ONLY_METHODS = frozenset({"get_work_item", "fetch_comments", "fetch_attachments",
                                "fetch_open_work_items"})  # Plan 241 F7: WIQL solo-lectura

# (C14) Lista EXPLICITA de campos. get_work_item(ado_id, fields=None) usa por default
# una lista hardcodeada de 7 campos que NO incluye System.Description. Probado: sin
# esta lista el ticket 367 devuelve la descripcion VACIA (0 chars) y el extractor de
# criterios no tiene nada que leer => todo run daria MIXED/NO_FUNCTIONAL_ASSERTION.
# Con la lista, el 367 devuelve 12.622 chars. Verificado tambien que ADO no devuelve
# 400 cuando un campo no existe para ese tipo: simplemente lo omite del dict.
_WORK_ITEM_FIELDS = [
    "System.Id", "System.Title", "System.State", "System.WorkItemType",
    "System.Parent", "System.AssignedTo", "System.ChangedDate", "System.Tags",
    "System.Description",
    "Microsoft.VSTS.Common.AcceptanceCriteria",
    "Microsoft.VSTS.TCM.ReproSteps",
]

_SOURCE = "stacky_dpapi"


def _ensure_backend_on_path() -> bool:
    if not _BACKEND.is_dir():
        return False
    p = str(_BACKEND)
    if p not in sys.path:
        sys.path.insert(0, p)
    return True


def bridge_available() -> bool:
    """True si el backend es importable Y hay PAT presente. NUNCA lanza."""
    try:
        if not _ensure_backend_on_path():
            return False
        from services.ado_client import ado_pat_present
        return bool(ado_pat_present())
    except Exception as exc:  # noqa: BLE001
        logger.debug("bridge_available False: %s", exc)
        return False


def _client():
    from services.ado_client import AdoClient
    return AdoClient()


def fetch_work_item(ticket_id: int) -> dict:
    """Lee un work item con el shape que espera uat_ticket_reader. NUNCA lanza."""
    try:
        if not _ensure_backend_on_path():
            return {"ok": False, "work_item": None, "source": _SOURCE,
                    "error": "backend_not_found", "message": str(_BACKEND)}
        wi = _client().get_work_item(int(ticket_id), fields=_WORK_ITEM_FIELDS)
        if not isinstance(wi, dict) or not wi.get("fields"):
            return {"ok": False, "work_item": None, "source": _SOURCE,
                    "error": "work_item_empty", "message": f"ticket {ticket_id} sin fields"}
        return {"ok": True, "work_item": wi, "source": _SOURCE,
                "error": None, "message": None,
                # Espejo del shape de ado.py get: el reader lee out["work_item"],
                # pero algunos callers historicos leen las keys al tope.
                "id": wi.get("id"), "fields": wi.get("fields")}
    except Exception as exc:  # noqa: BLE001
        logger.debug("fetch_work_item fallo: %s", exc, exc_info=True)
        return {"ok": False, "work_item": None, "source": _SOURCE,
                "error": type(exc).__name__, "message": str(exc)[:300]}


def fetch_children(parent_id: int) -> dict:
    """Hijas de un work item, por System.Parent. SOLO LECTURA (Plan 241 F7).

    Consulta WIQL de solo lectura: `WHERE [System.Parent] = <id>`. NUNCA lanza.
    Retorna {"ok": bool, "children": [{"ado_id", "title", "type", "state"}],
             "error": str|None}.
    """
    try:
        if not _ensure_backend_on_path():
            return {"ok": False, "children": [], "source": _SOURCE,
                    "error": "backend_not_found"}
        wiql = (
            "SELECT [System.Id] FROM WorkItems "
            f"WHERE [System.Parent] = {int(parent_id)} "
            "ORDER BY [System.Id] ASC"
        )
        items = _client().fetch_open_work_items(wiql) or []
        children = []
        for it in items:
            if not isinstance(it, dict):
                continue
            f = it.get("fields") or {}
            children.append({
                "ado_id": it.get("id") or f.get("System.Id"),
                "title": f.get("System.Title") or "",
                "type": f.get("System.WorkItemType") or "",
                "state": f.get("System.State") or "",
            })
        return {"ok": True, "children": children, "source": _SOURCE, "error": None}
    except Exception as exc:  # noqa: BLE001
        logger.debug("fetch_children fallo: %s", exc, exc_info=True)
        return {"ok": False, "children": [], "source": _SOURCE,
                "error": type(exc).__name__}


def fetch_comments(ticket_id: int, top: int = 20) -> dict:
    """Lee los comentarios de un work item. NUNCA lanza."""
    try:
        if not _ensure_backend_on_path():
            return {"ok": False, "comments": [], "source": _SOURCE, "error": "backend_not_found"}
        raw = _client().fetch_comments(int(ticket_id), top=int(top)) or []
        out = []
        for c in raw:
            if not isinstance(c, dict):
                continue
            created_by = c.get("createdBy") or {}
            out.append({
                "id": c.get("id"),
                "text": c.get("text") or c.get("content") or "",
                "author": created_by.get("displayName") if isinstance(created_by, dict) else "",
                "date": c.get("createdDate") or c.get("modifiedDate") or "",
            })
        return {"ok": True, "comments": out, "source": _SOURCE, "error": None}
    except Exception as exc:  # noqa: BLE001
        logger.debug("fetch_comments fallo: %s", exc, exc_info=True)
        return {"ok": False, "comments": [], "source": _SOURCE,
                "error": type(exc).__name__}
