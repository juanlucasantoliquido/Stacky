"""gitlab_variables.py — Plan 94. Adapter GitLab del sub-puerto de variables CI."""
from services.gitlab_provider import GitLabTrackerProvider
from services.tracker_provider import TrackerApiError


class GitLabVariablesProvider:
    """Adapter de variables CI para GitLab (project CI/CD variables API)."""

    name = "gitlab"

    def __init__(self, project: str | None):
        self._project = project
        self._provider = GitLabTrackerProvider(project_name=project)
        # C2: _request vive en gitlab_client.py:107 y devuelve TUPLA (body, status)
        self._client = self._provider._client

    def _project_path(self) -> str:
        """Resuelve el path del proyecto (pattern gitlab_provider.py:104)."""
        return self._client._project_path()

    def list_variables(self) -> list[dict]:
        """Lista variables del proyecto (sin values).

        C2: usa _request_paginated porque GET simple pagina de a 20.
        """
        proj = self._project_path()
        # C2: _request_paginated (gitlab_client.py:177) devuelve lista completa unida
        items = self._client._request_paginated("GET", f"/projects/{proj}/variables")

        result = []
        for v in items:
            # §4 C5: GitLab sin bit "secreta" separado de masked/protected.
            # Con protected:false fijo, una variable con masked:false es indistinguible
            # de una normal ⇒ is_secret vuelve False (limitación honesta del tracker).
            is_secret = bool(v.get("masked") or v.get("protected"))
            result.append({
                "key": v.get("key"),
                "is_secret": is_secret,
                "has_value": True,  # Si está en la lista, tiene valor
                "masked": v.get("masked"),
            })
        return result

    def set_variable(self, key: str, value: str, secret: bool) -> dict:
        """Crea o actualiza una variable (POST si no existe, PUT si existe).

        C3: detección de existencia con GET /variables/:key.
        C8: reintento determinista si masking rechazado (status 400).
        A3: envía raw=True para evitar expansión de $ en el value.
        """
        proj = self._project_path()

        try:
            # C3: detectar existencia con GET por key
            try:
                self._client._request("GET", f"/projects/{proj}/variables/{key}")
                exists = True
            except TrackerApiError as e:
                if e.status == 404:
                    exists = False
                else:
                    # Otro error (ej. 502) ⇒ propagar sanitizado
                    raise TrackerApiError(e.status, "Error al verificar existencia de variable", kind=e.kind)

            verb = "PUT" if exists else "POST"
            url = f"/projects/{proj}/variables/{key}" if exists else f"/projects/{proj}/variables"

            # A3: si secret=True, agregar raw:true (evita expansión de $)
            body = {
                "key": key,
                "value": value,
                "masked": secret,
                "protected": False,
            }
            if secret:
                body["raw"] = True

            # C8: reintento determinista si masking rechazado
            try:
                self._client._request(verb, url, json=body)
                masked_value = secret  # éxito con masked=true
            except TrackerApiError as e:
                # Si status 400 ⇒ posiblemente rejection de masking (valor no cumple reglas)
                if e.status == 400 and secret:
                    # Reintento ÚNICO con masked=false
                    retry_body = body.copy()
                    retry_body["masked"] = False
                    # A3: raw se conserva en el reintento (solo masking muta)
                    try:
                        self._client._request(verb, url, json=retry_body)
                        masked_value = False  # éxito con masked=false
                    except TrackerApiError:
                        raise TrackerApiError(400, "Valor no válido para variable masked", kind="masked_rejected")
                else:
                    # Otro error ⇒ propagar sanitizado (sin el value en el mensaje)
                    raise TrackerApiError(e.status, "Error al guardar variable", kind=e.kind)
        except TrackerApiError:
            raise
        except Exception:
            # 91 C1: excepción inesperada (en CUALQUIER paso, incl. el GET de existencia)
            # ⇒ mensaje genérico fijo (sin str(e), que podría contener el value).
            raise TrackerApiError(500, "Error interno de variables", kind="internal_error")

        return {
            "key": key,
            "is_secret": secret,
            "masked": masked_value,
        }

    def delete_variable(self, key: str) -> bool:
        """Borra una variable; False si no existía."""
        proj = self._project_path()

        try:
            self._client._request("DELETE", f"/projects/{proj}/variables/{key}")
            return True
        except TrackerApiError as e:
            if e.status == 404:
                return False
            raise TrackerApiError(e.status, "Error al borrar variable", kind=e.kind)
        except Exception:
            raise TrackerApiError(500, "Error interno de variables", kind="internal_error")
