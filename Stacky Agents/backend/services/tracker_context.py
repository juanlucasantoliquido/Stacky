"""services/tracker_context.py — Plan 289. Contexto de ticket POR PROVEEDOR.

Modulo HERMANO de services/ado_context.py. Su unica responsabilidad es leer los
comentarios de un ticket por la costura de proveedor (get_tracker_provider) y
devolverlos en la FORMA CANONICA que ado_context ya consume, con tope explicito.

NO arma bloques: eso lo hace ado_context, en un solo lugar, para los dos trackers
(P2 del plan). Dos armadores son dos oportunidades de divergir.

PURO respecto de la BD: no importa db, ni models, ni app.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("stacky_agents.tracker_context")

# Tope de comentarios que se traen al contexto. 30 y no otro numero: es EXACTAMENTE
# el `top=30` que usa el camino ADO (services/ado_context.py:229), asi que los dos
# trackers entregan la misma cantidad de contexto.
#
# NO es una flag registrada, a proposito: el modulo hermano ya tiene este idioma
# (ADO_CONTEXT_ATTACH_MAX_TEXT_FILES, ado_context.py:30-32 y :223) y subir este
# numero no es una decision de producto sino una forma de reventar la ventana de
# contexto. La env var existe como valvula de emergencia, no como configuracion.
_DEFAULT_MAX_COMMENTS = 30
_ENV_MAX_COMMENTS = "TRACKER_CONTEXT_MAX_COMMENTS"


def max_comments() -> int:
    raw = (os.environ.get(_ENV_MAX_COMMENTS) or "").strip()
    if not raw:
        return _DEFAULT_MAX_COMMENTS
    try:
        valor = int(raw)
    except ValueError:
        logger.warning(
            "tracker_context — %s='%s' no es int, usando %d",
            _ENV_MAX_COMMENTS, raw, _DEFAULT_MAX_COMMENTS,
        )
        return _DEFAULT_MAX_COMMENTS
    return max(0, valor)


def normalizar_notas_gitlab(notas) -> list[dict]:
    """Nota cruda de GitLab -> forma canonica {author, date, text, is_html}.

    FUNCION PURA. Mapeo (claves reales verificadas en gitlab_provider.py:651-653):
      body       -> text     (Markdown, NO HTML -> is_html=False)
      author.name -> author  (cae a author.username, y despues a "?"; espeja el
                              displayName -> uniqueName -> "?" de ado_client.py:452-453)
      created_at -> date     (recortado a 10 chars, igual que ado_client.py:454)

    Descarta: notas sin texto y notas `system` (el provider ya las filtra en
    gitlab_provider.py:468-469; aca no se confia en eso).
    """
    salida: list[dict] = []
    for nota in notas or []:
        if not isinstance(nota, dict):
            continue
        if nota.get("system"):
            continue
        texto = (nota.get("body") or "").strip()
        if not texto:
            continue
        autor_raw = nota.get("author")
        autor_dict = autor_raw if isinstance(autor_raw, dict) else {}
        autor = (autor_dict.get("name") or autor_dict.get("username") or "?").strip() or "?"
        fecha = (nota.get("created_at") or "")[:10]
        salida.append({"author": autor, "date": fecha, "text": texto, "is_html": False})
    return salida


def fetch_comentarios_normalizados(
    *, project_name: str | None, item_id, log=None,
) -> tuple[list[dict], dict]:
    """Comentarios de un ticket, por la costura de proveedor, ya normalizados y topeados.

    `item_id` es el id que el proveedor entiende. Para GitLab es el **iid**, que en
    Stacky vive en `Ticket.ado_id` (gitlab_sync.py:145). Se convierte a str porque
    GitLabTrackerProvider.fetch_comments espera str (gitlab_provider.py:472).

    NUNCA levanta. Devuelve (comentarios, stats) donde stats declara el motivo de
    todo lo que no se pudo hacer: un contexto vacio SIN explicacion es el defecto
    que este plan cierra.
    """
    stats: dict = {
        "comments_count": 0,
        "comments_truncated": False,
        # v2 — cuantos habia ANTES de recortar. Lo consume el sello del bloque (F5/F6):
        # sin este numero el bloque puede decir "30 comentarios" y el agente creer que
        # esos son TODOS, que es exactamente el trabajo a ciegas que el plan cierra.
        "comments_total_disponibles": 0,
        "errors": [],
    }

    # Import LOCAL y por MODULO (no `from ... import get_tracker_provider`): los
    # tests parchean el atributo del modulo, y un import por nombre congelaria la
    # referencia al cargar. Mismo motivo por el que tracker_provider.py:121 importa
    # `resolve_project_context` a nivel modulo "para poder parchear en tests".
    from services import tracker_provider as _tp

    try:
        provider = _tp.get_tracker_provider(project_name)
    except Exception as exc:  # noqa: BLE001
        stats["errors"].append(f"tracker_provider_unavailable: {exc}")
        return [], stats

    fetch = getattr(provider, "fetch_comments", None)
    if not callable(fetch):
        stats["errors"].append(
            f"capability_missing: el proveedor '{getattr(provider, 'name', '?')}' "
            f"no expone fetch_comments"
        )
        return [], stats

    try:
        crudos = fetch(str(item_id))
    except Exception as exc:  # noqa: BLE001
        stats["errors"].append(f"fetch_comments_failed: {exc}")
        return [], stats

    comentarios = normalizar_notas_gitlab(crudos)
    stats["comments_total_disponibles"] = len(comentarios)   # v2: ANTES de recortar

    tope = max_comments()
    if len(comentarios) > tope:
        # Se conservan las MAS RECIENTES: GitLab devuelve las notas de mas vieja a
        # mas nueva, y el contexto util de un ticket es el final de la conversacion.
        # Es la misma politica que ADO, que pide `order=desc` con $top (ado_client.py:439).
        stats["comments_truncated"] = True
        comentarios = comentarios[len(comentarios) - tope:]

    stats["comments_count"] = len(comentarios)
    if log:
        log("info", f"tracker_context — {len(comentarios)} comentarios "
                    f"(tope={tope}, recortado={stats['comments_truncated']})")
    return comentarios, stats
