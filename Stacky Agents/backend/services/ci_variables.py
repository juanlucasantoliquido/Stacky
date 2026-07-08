"""ci_variables.py — Plan 94. Sub-puerto de variables CI + helpers PUROS.
Los helpers no hacen I/O. El VALOR de un secreto jamás se loggea ni retorna."""
import re
from typing import Optional, Protocol, runtime_checkable

_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SECRET_HINT_RE = re.compile(
    r"(PASSWORD|PASSWD|PWD|SECRET|TOKEN|APIKEY|API_KEY|PRIVATE|CRED(?!IT)|CONN(ECTION)?_?STR)",
    re.IGNORECASE,
)


def validate_variable_key(key: str) -> str | None:
    """Valida una key de variable CI.

    Retorna None si la key es válida; si no, retorna un mensaje de error en llano.
    Reglas (constraint de GitLab; ADO las tolera):
    - Debe empezar con letra o underscore
    - El resto son letras, dígitos o underscores
    - Longitud 1..255 caracteres
    """
    if not key:
        return "La key no puede estar vacía"
    if len(key) > 255:
        return "La key excede los 255 caracteres"
    if not _KEY_RE.match(key):
        return "La key debe empezar con letra o '_' y contener solo letras, dígitos y '_'"
    return None


def looks_secret(key: str) -> bool:
    """Heurística: True si el NOMBRE sugiere secreto.

    Solo por key, nunca por valor (write-only). Casos típicos:
    PASSWORD, TOKEN, APIKEY, PRIVATE_KEY, CONNECTION_STRING, etc.
    """
    return bool(_SECRET_HINT_RE.search(key))


class VariablesUnavailableError(Exception):
    """El tracker no puede alojar variables todavía (ADO sin definición) → 409."""


@runtime_checkable
class CIVariablesProvider(Protocol):
    """Protocolo del sub-puerto de variables CI."""

    name: str

    def list_variables(self) -> list[dict]:
        """Lista variables del proyecto (sin values)."""
        ...

    def set_variable(self, key: str, value: str, secret: bool) -> dict:
        """Crea o actualiza una variable."""
        ...

    def delete_variable(self, key: str) -> bool:
        """Borra una variable; False si no existía."""
        ...


VARIABLES_PORT_METHODS = ("list_variables", "set_variable", "delete_variable")


def get_variables_provider(project: Optional[str] = None) -> CIVariablesProvider:
    """Fábrica espejo EXACTO de get_ci_provider (ci_provider.py:107-129).

    resolve_project_context por tracker_type; TODOS los imports (project_context,
    config, adapters) son LAZY, DENTRO de la función (C9 — mantiene verde el grep
    de test_f1_pure_no_io). gitlab -> GitLabVariablesProvider;
    azure_devops -> AdoVariablesProvider; otro -> TrackerConfigError.
    """
    from services.project_context import resolve_project_context  # noqa: PLC0415
    from services.tracker_provider import TrackerConfigError  # noqa: PLC0415
    import config as _config  # noqa: PLC0415

    ctx = resolve_project_context(project_name=project)
    tracker_type = (getattr(ctx, "tracker_type", None) or "azure_devops").strip().lower()

    if tracker_type == "gitlab":
        if not getattr(_config.config, "STACKY_GITLAB_ENABLED", False):
            raise TrackerConfigError(
                "issue_tracker.type=gitlab pero STACKY_GITLAB_ENABLED=false"
            )
        from services.gitlab_variables import GitLabVariablesProvider  # noqa: PLC0415
        return GitLabVariablesProvider(project=project)
    elif tracker_type == "azure_devops":
        from services.ado_variables import AdoVariablesProvider  # noqa: PLC0415
        return AdoVariablesProvider(project=project)
    else:
        raise TrackerConfigError(
            f"El tracker type '{tracker_type}' no soporta variables CI. "
            f"Requiere 'gitlab' o 'azure_devops'."
        )

