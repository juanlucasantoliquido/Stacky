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
