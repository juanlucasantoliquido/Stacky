"""
services/tracker_provider.py -- Puerto TrackerProvider (Plan 65).

Define el protocolo formal (Port) que todos los adaptadores de tracker deben
implementar, más la fábrica get_tracker_provider() que selecciona el adapter
correcto según issue_tracker.type del proyecto.

Tipos soportados:
  azure_devops → AdoTrackerProvider  (always available)
  gitlab       → GitLabTrackerProvider (requires STACKY_GITLAB_ENABLED=true)

Tipos con path de sync existente (jira, mantis) se rechazan — usen su integración
directa; no redirigir por este puerto todavía.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable, Optional


@dataclass(frozen=True)
class TrackerQuery:
    state: str = "open"
    labels: tuple[str, ...] = ()
    milestone: Optional[str] = None
    assignee: Optional[str] = None
    search: Optional[str] = None
    parent_id: Optional[str] = None
    # Plan 292 — ISO-8601 del tracker; None = sin filtro. Va ULTIMO y con default
    # a proposito: los 6 llamadores de produccion siguen andando sin tocarse, y un
    # proveedor que no lo entienda simplemente lo ignora.
    updated_after: Optional[str] = None


@dataclass(frozen=True)
class TrackerItem:
    item_type: str
    title: str
    description_html: str
    labels: tuple[str, ...] = ()
    assignee: Optional[str] = None
    parent_id: Optional[str] = None
    fields: dict = field(default_factory=dict)


class TrackerError(RuntimeError): ...


class TrackerConfigError(TrackerError): ...


class TrackerApiError(TrackerError):
    def __init__(self, status: int, message: str, *, kind: str = "unknown"):
        super().__init__(message)
        self.status = status
        self.kind = kind


class CapabilityUnavailable(TrackerError):
    """La capacidad no existe (o es parcial) en el proveedor activo. NO es un bug.

    Plan 218 F2 (§3.1 la congela acá porque F3 la necesita y corre antes que F6).
    F6 agrega su traducción HTTP: 200 + {"available": false, ...}, nunca un 500 mudo.
    """

    def __init__(self, capability: str, provider: str, *, reason: str, workaround: str = ""):
        super().__init__(f"'{capability}' no disponible en {provider}: {reason}")
        self.capability = capability
        self.provider = provider
        self.reason = reason
        self.workaround = workaround

    def to_payload(self) -> dict:
        return {"available": False, "capability": self.capability,
                "provider": self.provider, "reason": self.reason,
                "workaround": self.workaround}


@runtime_checkable
class TrackerProvider(Protocol):
    name: str

    def credentials_present(self) -> bool: ...
    def get_authenticated_user(self) -> dict: ...
    def fetch_open_items(self, query: TrackerQuery) -> list[dict]: ...
    def get_item(self, item_id: str) -> dict: ...
    def item_url(self, item_id: str) -> str: ...
    def fetch_states(self) -> list[str]: ...
    def update_item_state(self, item_id: str, logical_state: str) -> dict: ...
    def fetch_comments(self, item_id: str) -> list[dict]: ...
    def fetch_all_comments(self, item_id: str) -> list[dict]: ...
    def post_comment(self, item_id: str, body_html: str) -> dict: ...
    def comment_exists(self, item_id: str, marker: str) -> bool: ...
    def create_item(self, item: TrackerItem) -> dict: ...
    def find_child_by_marker(self, parent_id: str, marker: str) -> Optional[dict]: ...
    def update_item_assignee(self, item_id: str, assignee: str) -> dict: ...
    def fetch_attachments(self, item_id: str) -> list[dict]: ...
    def upload_attachment(self, file_path: str, file_name: str) -> dict: ...
    def link_attachment(self, item_id: str, attachment: dict) -> dict: ...
    def fetch_item_updates(self, item_id: str, since: Optional[str] = None) -> list[dict]: ...


PORT_METHODS: tuple[str, ...] = (
    "credentials_present",
    "get_authenticated_user",
    "fetch_open_items",
    "get_item",
    "item_url",
    "fetch_states",
    "update_item_state",
    "fetch_comments",
    "fetch_all_comments",
    "post_comment",
    "comment_exists",
    "create_item",
    "find_child_by_marker",
    "update_item_assignee",
    "fetch_attachments",
    "upload_attachment",
    "link_attachment",
    "fetch_item_updates",
)

# Importados a nivel módulo para poder parchear en tests
from services.project_context import resolve_project_context  # noqa: E402
import config  # noqa: E402


def get_tracker_provider(project: Optional[str] = None):
    """Fábrica: selecciona adapter por issue_tracker.type del proyecto."""
    ctx = resolve_project_context(project_name=project)
    ttype = (getattr(ctx, "tracker_type", None) or "azure_devops").strip().lower()

    if ttype == "gitlab":
        # P5 / D1 (Plan 218 F0): la flag vive en la INSTANCIA (config.py:1631
        # `config = Config()`), no en el módulo. Mismo patrón que ci_provider.py:121.
        if not bool(getattr(config.config, "STACKY_GITLAB_ENABLED", False)):
            raise TrackerConfigError(
                "issue_tracker.type=gitlab pero STACKY_GITLAB_ENABLED=false"
            )
        from services.gitlab_provider import GitLabTrackerProvider
        # Plan 218 F4 (B1): el destino se resuelve POR PROYECTO. Antes se pasaba el
        # NOMBRE Stacky ("RSPACIFICO") a un constructor que lo interpreta como path
        # de proyecto GitLab.
        if bool(getattr(config.config, "STACKY_TRACKER_TARGET_PER_PROJECT_ENABLED", True)):
            from services.project_context import build_tracker_target
            tgt = build_tracker_target(project)
            return GitLabTrackerProvider(
                project=tgt.project_path, base_url=tgt.base_url,
                group=tgt.group, auth_path=tgt.auth_path,
                ca_bundle=tgt.ca_bundle,
            )
        # Plan 276 F8.1 — la ruta legacy TAMBIÉN necesita el bundle: sin él, apagar
        # STACKY_TRACKER_TARGET_PER_PROJECT_ENABLED devuelve el SSLError entero
        # contra un GitLab con certificado interno. Era el único camino del repo que
        # construía este provider sin certificado y no tenía ningún test.
        return GitLabTrackerProvider(
            project=project,
            ca_bundle=(getattr(config.config, "STACKY_GITLAB_CA_BUNDLE", "") or None),
        )

    if ttype == "azure_devops":
        from services.ado_provider import AdoTrackerProvider
        return AdoTrackerProvider(project=project)

    raise TrackerConfigError(
        f"tracker '{ttype}' sin puerto formal (usa su path de sync existente)"
    )


# ── Plan 282 F2 — un solo constructor de GitLabTrackerProvider ───────────────
# Cuatro servicios (gitlab_ci_logs, gitlab_ci_provider, gitlab_preflight,
# gitlab_variables) construian el provider A MANO con `GitLabTrackerProvider(
# project=project)`. Ese constructor NO resuelve el `ca_bundle`, asi que contra
# un GitLab self-hosted con CA interna morian con CERTIFICATE_VERIFY_FAILED
# mientras la sonda y el listado de tickets funcionaban: una parte del producto
# anda y otra no, sin explicacion visible. Aca esta el UNICO constructor.


def gitlab_factory_only_enabled() -> bool:
    """STACKY_GITLAB_PROVIDER_FACTORY_ONLY_ENABLED (default True).

    Kill-switch de reversibilidad: con OFF, los 4 servicios vuelven al camino
    byte-identico al previo al plan 282 (sin ca_bundle).
    """
    return bool(getattr(
        config.config, "STACKY_GITLAB_PROVIDER_FACTORY_ONLY_ENABLED", True,
    ))


def build_gitlab_provider(project: Optional[str] = None):
    """Devuelve el GitLabTrackerProvider del proyecto, SIEMPRE con ca_bundle.

    Orden de resolucion:
      1. Flag OFF -> construccion directa (camino viejo, reversibilidad).
      2. `get_tracker_provider(project)` -> si devuelve el provider GitLab, ese
         gana: trae base_url, group, auth_path y ca_bundle POR PROYECTO.
      3. La fabrica devolvio OTRO proveedor (el proyecto no usa GitLab) ->
         TrackerConfigError. Error TIPADO del modulo, nunca un AttributeError
         mas abajo cuando alguien pida `_client._project_path()`.
      4. La fabrica no pudo resolver el contexto (proyecto sin configurar) ->
         se construye igual, pero NUNCA sin bundle: cae al global
         STACKY_GITLAB_CA_BUNDLE. Degradar sin certificado es el bug original.
    """
    from services.gitlab_provider import GitLabTrackerProvider

    if not gitlab_factory_only_enabled():
        return GitLabTrackerProvider(project=project)

    try:
        proveedor = get_tracker_provider(project)
    except TrackerConfigError:
        proveedor = None
    except Exception:  # noqa: BLE001 — contexto irresoluble: se degrada abajo
        proveedor = None

    if proveedor is not None:
        # Sin isinstance: bajo `patch(...)` la clase es un MagicMock y isinstance
        # levanta TypeError. Se compara el NOMBRE de la clase concreta.
        if type(proveedor).__name__ == "GitLabTrackerProvider":
            return proveedor
        raise TrackerConfigError(
            f"el proyecto '{project}' no usa GitLab "
            f"(proveedor resuelto: {type(proveedor).__name__})"
        )

    return GitLabTrackerProvider(
        project=project,
        ca_bundle=(getattr(config.config, "STACKY_GITLAB_CA_BUNDLE", "") or None),
    )
