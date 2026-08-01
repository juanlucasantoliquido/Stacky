"""Plan 282 F1 — A que tracker le corresponde recibir el comentario del agente.

Modulo PURO de ruteo: sin Flask, sin sesion de BD, sin estado global. Espeja la
forma REAL de services/tracker_write_router.py `resolve_state_writer` — que
recibe el TICKET y devuelve un handle, no un Callable suelto. Recibe el ticket
(y no el tracker_type) porque el provider GitLab se construye POR PROYECTO:
services/tracker_provider.py `get_tracker_provider(project)` y
`GitLabTrackerProvider(project=, base_url=, group=, auth_path=, ca_bundle=)`
necesitan el proyecto; con solo el tipo se terminaria escribiendo en el proyecto
GitLab equivocado.

[ADICION ARQUITECTO A1] El router NO devuelve "un publicador": devuelve un objeto
con la FORMA DEL CLIENTE ADO. Todo lo que services/ado_publisher.py hace entre la
resolucion del cliente y la persistencia trabaja contra una variable `client` y
solo le pide tres cosas: `post_comment(id, html, "html")`, `comment_exists(id,
marker)` y (opcional) `upload_attachment(path, file_name=...)`. Al devolver un
adaptador con esa forma, el dedupe por sha, el dedupe por marcador, la inyeccion
del marcador y la persistencia funcionan para GitLab sin tocarlos, y el mismatch
de aridad se vuelve imposible por construccion.

REGLA DURA, copiada literal del write router: nunca devuelve kind == "ado_client"
cuando el tracker_type normalizado no es "azure_devops" (ni vacio/None).
"""
from __future__ import annotations

from dataclasses import dataclass

# Clave declarada en services/provider_capabilities.py (familia tracker.items.*).
CAPABILITY_PUBLISH_COMMENT = "tracker.items.post_comment"

# El texto NOMBRA la flag literal: el operador tiene que poder actuar sin abrir
# el codigo (mismo criterio que tracker_write_router.GITLAB_FLAG_WORKAROUND).
GITLAB_FLAG_WORKAROUND = (
    "activa STACKY_GITLAB_ENABLED en Configuracion > Arnes para que "
    "Stacky pueda publicar el comentario en GitLab; hasta entonces el "
    "resultado queda solo en el archivo comment.html del workspace."
)

_ADO_TRACKER_TYPES: frozenset[str] = frozenset({"", "azure_devops"})


@dataclass(frozen=True)
class CommentPublisher:
    tracker_type: str          # "azure_devops" | "gitlab"
    kind: str                  # "ado_client" | "gitlab_adapter"
    handle: object             # SIEMPRE con la forma del cliente ADO


class GitLabCommentClient:
    """Adaptador: habla el dialecto que `ado_publisher` ya usa.

    Existe por UNA razon medible: ado_publisher llama
    `client.post_comment(ado_id, html, "html")` con TRES posicionales, y
    `GitLabTrackerProvider.post_comment(item_id, body_html)` acepta DOS. Sin el
    adaptador la primera corrida real muere con TypeError, y ningun test unitario
    del proveedor lo ve: el puerto declara el NOMBRE del metodo, no su firma.
    """

    def __init__(self, provider):
        self._p = provider

    # ── lo que ado_publisher le pide al `client` ──────────────────────────────

    def post_comment(self, item_id, body_html, content_format="html") -> dict:
        """`content_format` se ACEPTA y se IGNORA.

        El provider ya convierte el HTML a markdown en `_render_note`. Se acepta
        el tercer posicional para que la llamada de ado_publisher no cambie.

        DEBE devolver un dict con clave "id": ado_publisher exige `comment_id` en
        la respuesta o levanta RuntimeError. La API de notas de GitLab devuelve
        {"id": ...} y post_comment lo pasa tal cual.
        """
        resultado = self._p.post_comment(str(item_id), body_html)
        return resultado if isinstance(resultado, dict) else {}

    def comment_exists(self, item_id, marker):
        """La consume ado_publisher por `getattr(client, "comment_exists", None)`.

        NO se escribe un segundo chequeo de idempotencia: el que ya existe en el
        publicador es generico y cubre GitLab por este metodo.

        Contrato del llamador: trata cualquier valor NO-None como "ya existe".
        `GitLabTrackerProvider.comment_exists` devuelve bool, asi que un False
        pelado seria interpretado como "existe". Se normaliza a None cuando no
        existe.
        """
        existe = self._p.comment_exists(str(item_id), marker)
        return existe if existe else None

    def upload_attachment(self, file_path, file_name=None):
        """Adjuntos: delega si el provider sabe; si no, degrada declarando.

        `_prepare_html_attachments` solo pide esto (y, opcionalmente,
        `link_attachment_to_work_item`, que GitLab no tiene: el summary sale con
        linked=0). Si el provider no expone el metodo, se levanta un error
        tipado que el publicador ya captura como AttachmentPublishError.
        """
        fn = getattr(self._p, "upload_attachment", None)
        if not callable(fn):
            raise RuntimeError(
                "el proveedor GitLab no expone upload_attachment: "
                "el comentario tiene adjuntos que no se pueden subir"
            )
        return fn(str(file_path), file_name or "")


def routing_enabled() -> bool:
    """STACKY_COMMENT_PUBLISH_ROUTED_ENABLED (default True).

    Se lee de la INSTANCIA `config.config`, no del modulo: es el patron vivo del
    repo (tracker_provider.py) y el unico que respeta el override en caliente.
    """
    from config import config as _cfg
    return bool(getattr(_cfg, "STACKY_COMMENT_PUBLISH_ROUTED_ENABLED", True))


def _norm_tracker_type(ticket) -> str:
    raw = getattr(ticket, "tracker_type", None)
    if not isinstance(raw, str):
        return ""
    return raw.strip().lower()


def resolve_comment_publisher(ticket) -> CommentPublisher:
    """Devuelve el publicador de comentarios del tracker del TICKET, o levanta.

    - tracker_type ausente / "azure_devops" -> kind="ado_client" con el cliente
      que el publicador construye HOY (incluido su fallback al cliente por
      defecto cuando el ticket no tiene stacky_project_name). Camino sin cambios.
    - tracker_type == "gitlab" -> kind="gitlab_adapter" envolviendo
      get_tracker_provider(stacky_project_name). Si esa fabrica levanta
      TrackerConfigError (p.ej. STACKY_GITLAB_ENABLED=false) se RE-LEVANTA como
      CapabilityUnavailable. NUNCA se cae a ADO.
    - cualquier otro tracker -> CapabilityUnavailable (el llamador lo traduce a
      PublishResult(ok=False, error_kind="publisher_unavailable"), no revienta).
    """
    from services.tracker_provider import CapabilityUnavailable, TrackerConfigError

    ttype = _norm_tracker_type(ticket)

    if ttype in _ADO_TRACKER_TYPES:
        # Import local (evita el ciclo router <-> publicador) y REUSA el helper
        # del publicador para que el camino ADO quede byte-identico, fallback al
        # cliente por defecto incluido.
        from services import ado_publisher
        handle = ado_publisher._client_for_ticket_project(
            stacky_project_name=getattr(ticket, "stacky_project_name", None),
            tracker_project=getattr(ticket, "project", None),
        )
        return CommentPublisher(
            tracker_type="azure_devops", kind="ado_client", handle=handle,
        )

    if ttype == "gitlab":
        from services import tracker_provider
        try:
            provider = tracker_provider.get_tracker_provider(
                getattr(ticket, "stacky_project_name", None)
            )
        except TrackerConfigError as exc:
            raise CapabilityUnavailable(
                CAPABILITY_PUBLISH_COMMENT,
                "gitlab",
                reason=f"el proveedor GitLab no esta disponible: {exc}",
                workaround=GITLAB_FLAG_WORKAROUND,
            ) from exc
        return CommentPublisher(
            tracker_type="gitlab",
            kind="gitlab_adapter",
            handle=GitLabCommentClient(provider),
        )

    raise CapabilityUnavailable(
        CAPABILITY_PUBLISH_COMMENT,
        ttype or "desconocido",
        reason=f"tracker '{ttype}' sin publicador de comentarios",
    )


def clasificar_error_de_publicacion(exc) -> str:
    """Clasifica el fallo del POST del comentario.

    - "tracker_error": fallo TIPADO del tracker (jerarquia TrackerError). Sale
      diciendo que fue del tracker, no disfrazado de "ADO post_comment failed".
    - "exception": cualquier otro. Es el comportamiento de hoy para ADO, que
      queda intacto (AdoClient no levanta TrackerError en ningun camino).
    """
    try:
        from services.tracker_provider import TrackerError
    except Exception:  # noqa: BLE001 — clasificar jamas puede tumbar el cierre
        return "exception"
    return "tracker_error" if isinstance(exc, TrackerError) else "exception"
