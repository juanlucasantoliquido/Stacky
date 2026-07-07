"""ado_preflight.py — Plan 93 F2. Adapter AdoPreflightProvider.

Implementa CIPreflightProvider (services/ci_preflight.py) usando AdoClient.
"""
from __future__ import annotations

_MAX_POOLS = 25  # [C12] cap explícito — el click no cuelga
_DETAIL_SANITIZE_LEN = 500  # [C13]


class AdoPreflightProvider:
    """CIPreflightProvider para Azure DevOps."""

    name = "azure_devops"

    def __init__(self, project: str | None = None) -> None:
        # Lazy: NO construye AdoClient acá (patrón AdoCIProvider, ado_ci_provider.py:17-18)
        # — evita I/O/auth en __init__; se construye recién al primer uso real.
        self._project = project
        self.__client: object | None = None

    @property
    def _client(self):
        if self.__client is None:
            from services.ado_client import AdoClient  # noqa: PLC0415
            self.__client = AdoClient(project=self._project)
        return self.__client

    @_client.setter
    def _client(self, value) -> None:
        """Setter para tests (patrón repo_writer: provider._client = mock_client)."""
        self.__client = value

    def lint_yaml(self, yaml_str: str) -> dict:
        """Preview-run: POST {base_proj}/_apis/pipelines/{did}/preview con
        {"previewRun": true, "yamlOverride": yaml_str} — dry-run por contrato
        ADO (NO encola). Si no hay pipeline definition, degrada a unavailable
        con CTA al plan 95."""
        from services.ado_pipeline_definitions import find_yaml_definition  # noqa: PLC0415

        definition = find_yaml_definition(self._project)
        if definition is None:
            return {
                "status": "unavailable",
                "errors": [],
                "detail": (
                    "ADO todavía no tiene una pipeline definition para "
                    "azure-pipelines.yml — creala con 'Llevar a producción' "
                    "(plan 95) o en la web de ADO; mientras tanto se valida "
                    "localmente."
                ),
            }
        try:
            url = (
                f"{self._client._base_proj}/_apis/pipelines/"
                f"{definition['id']}/preview?api-version=7.1"
            )
            self._client._request(
                "POST", url, {"previewRun": True, "yamlOverride": yaml_str}
            )
            return {"status": "ok", "errors": [], "detail": "YAML válido para Azure DevOps"}
        except Exception as exc:  # 400 con mensaje de YAML -> fail; otra excepción -> unavailable
            detail = str(exc)[:_DETAIL_SANITIZE_LEN]
            status_code = getattr(exc, "status_code", None)
            if status_code == 400:
                return {"status": "fail", "errors": [detail], "detail": detail}
            return {"status": "unavailable", "errors": [], "detail": detail}

    def list_runners(self) -> dict:
        """GET {base_org}/_apis/distributedtask/pools?api-version=7.1 (máximo 25
        pools) + por cada pool self-hosted GET .../pools/{id}/agents. Pools
        hosted (isHosted) -> entrada ok/hosted sin verificar agentes."""
        try:
            base_org = self._client._base_proj.rsplit("/", 1)[0]
            pools_url = f"{base_org}/_apis/distributedtask/pools?api-version=7.1"
            pools_body = self._client._request("GET", pools_url)
        except Exception as exc:
            return {"status": "unavailable", "runners": [], "detail": str(exc)[:_DETAIL_SANITIZE_LEN]}

        pools = (pools_body.get("value") or [])[:_MAX_POOLS]
        runners: list[dict] = []

        for pool in pools:
            pool_id = pool.get("id")
            if pool.get("isHosted"):
                runners.append({
                    "id": pool_id,
                    "online": True,
                    "tags": ["hosted"],
                    "detail": "pool Microsoft-hosted: disponibilidad no verificable, se asume ok (ámbar)",
                })
                continue
            try:
                agents_url = f"{base_org}/_apis/distributedtask/pools/{pool_id}/agents?api-version=7.1"
                agents_body = self._client._request("GET", agents_url)
                agents = agents_body.get("value") or []
                any_online = any(
                    (a.get("status") == "online") and a.get("enabled", True) for a in agents
                )
                runners.append({
                    "id": pool_id,
                    "online": any_online,
                    "tags": [],
                    "detail": (
                        "ADO agrupa por pool, no por tags — se verifica que el "
                        "pool tenga al menos 1 agente online"
                    ),
                })
            except Exception:
                runners.append({"id": pool_id, "online": False, "tags": None})

        return {"status": "ok", "runners": runners, "detail": ""}
