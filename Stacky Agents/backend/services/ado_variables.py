"""ado_variables.py — Plan 94. Adapter ADO del sub-puerto de variables CI."""
from services.ado_client import AdoClient
from services.ado_pipeline_definitions import find_yaml_definition
from services.tracker_provider import TrackerApiError


class AdoVariablesProvider:
    """Adapter de variables CI para Azure DevOps (variables de pipeline definition)."""

    name = "azure_devops"

    def __init__(self, project: str | None):
        self._project = project
        self._client = AdoClient._request  # C2: _request devuelve (body, status)

        # C4: buscar la pipeline definition; si no existe ⇒ VariablesUnavailableError
        self._definition = find_yaml_definition(project)
        if self._definition is None:
            from services.ci_variables import VariablesUnavailableError
            raise VariablesUnavailableError(
                "ADO sin pipeline definition para azure-pipelines.yml — "
                "creala con 'Llevar a producción' (plan 95) o en la web de ADO."
            )

    def list_variables(self) -> list[dict]:
        """Lista variables de la definition (sin values)."""
        # GET del detalle completo de la definition
        base_proj = self._project  # ADO usa project name directo
        def_id = self._definition["id"]
        url = f"{base_proj}/_apis/build/definitions/{def_id}?api-version=7.1"
        body, status = self._client("GET", url)

        # C11: el campo "variables" puede faltar
        variables = body.get("variables") or {}

        result = []
        for key, var_def in variables.items():
            is_secret = bool(var_def.get("isSecret"))
            result.append({
                "key": key,
                "is_secret": is_secret,
                "has_value": True,  # Si está en la definition, tiene valor
                "masked": None,  # ADO no tiene concepto de masking
            })
        return result

    def set_variable(self, key: str, value: str, secret: bool) -> dict:
        """Crea o actualiza una variable en la definition.

        C4: PUT full-definition con el campo revision intacto.
        C12: NO borra secretos hermanos (value:null se conserva byte-idéntico).
        """
        base_proj = self._project
        def_id = self._definition["id"]
        url = f"{base_proj}/_apis/build/definitions/{def_id}?api-version=7.1"

        try:
            # GET del detalle completo
            body, _ = self._client("GET", url)

            # C11: el campo "variables" puede faltar
            variables = body.get("variables") or {}

            # C4 + C12: mutar el JSON del GET in place (NO reconstruir)
            # Regla ANTI-WIPE: toda entrada preexistente viaja byte-idéntica
            variables[key] = {
                "value": value,
                "isSecret": secret,
                "allowOverride": False,
            }

            # PUT con el documento completo (incluido el revision tal cual vino)
            self._client("PUT", url, json=body)
        except TrackerApiError as e:
            # Rechazo por revision desactualizada (409/400) u otro fallo del GET/PUT
            # ⇒ propagar sanitizado (sin el value).
            raise TrackerApiError(e.status, "Error al guardar variable en ADO", kind=e.kind)
        except Exception:
            # 91 C1: excepción inesperada en CUALQUIER paso ⇒ mensaje genérico fijo.
            raise TrackerApiError(500, "Error interno de variables", kind="internal_error")

        return {
            "key": key,
            "is_secret": secret,
            "masked": None,  # ADO no tiene masking
        }

    def delete_variable(self, key: str) -> bool:
        """Borra una variable de la definition; False si no existía."""
        base_proj = self._project
        def_id = self._definition["id"]
        url = f"{base_proj}/_apis/build/definitions/{def_id}?api-version=7.1"

        # GET del detalle
        body, _ = self._client("GET", url)
        variables = body.get("variables") or {}

        if key not in variables:
            return False

        # Borrar y PUT
        del variables[key]
        try:
            self._client("PUT", url, json=body)
        except TrackerApiError as e:
            raise TrackerApiError(e.status, "Error al borrar variable en ADO", kind=e.kind)
        except Exception:
            raise TrackerApiError(500, "Error interno de variables", kind="internal_error")
        return True
