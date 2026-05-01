"""
Cliente Azure DevOps para Stacky Agents.

Trae work items reales del proyecto configurado (default: UbimiaPacifico/Strategist_Pacifico).
Sin dependencias extra — usa urllib stdlib.

PAT se resuelve en este orden:
  1. env ADO_PAT
  2. Tools/PAT-ADO (formato {"pat": "...", "pat_format": "preencoded|raw"})
  3. Tools/Stacky/auth/ado_auth.json (mismo formato, compatibilidad)
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from config import config

logger = logging.getLogger("stacky_agents.ado")

_API_VERSION = "7.1"
_TIMEOUT_SEC = 30
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_TOOLS_ROOT = _BACKEND_ROOT.parent.parent

_DEFAULT_WIQL = (
    "SELECT [System.Id] FROM WorkItems "
    "WHERE [System.TeamProject] = @project "
    "AND [System.State] NOT IN ('Closed', 'Done', 'Removed', 'Completed') "
    "ORDER BY [System.ChangedDate] DESC"
)

_B64_RE = re.compile(r"^[A-Za-z0-9+/=]+$")


class AdoConfigError(RuntimeError):
    pass


class AdoApiError(RuntimeError):
    pass


def _looks_preencoded(raw: str) -> bool:
    return len(raw) >= 80 and bool(_B64_RE.match(raw))


def _read_pat_file(path: Path) -> str | None:
    try:
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.debug("No se pudo leer %s: %s", path, e)
        return None
    raw = (data.get("pat") or "").strip()
    if not raw:
        return None
    fmt = (data.get("pat_format") or "").strip().lower()
    if fmt == "preencoded" or _looks_preencoded(raw):
        return raw
    return base64.b64encode(f":{raw}".encode("utf-8")).decode("ascii")


def _resolve_auth_header() -> str:
    raw_env = (os.environ.get("ADO_PAT") or config.ADO_PAT or "").strip()
    if raw_env:
        if _looks_preencoded(raw_env):
            return f"Basic {raw_env}"
        return f"Basic {base64.b64encode(f':{raw_env}'.encode()).decode('ascii')}"

    candidates = [
        _TOOLS_ROOT / "PAT-ADO",
        _TOOLS_ROOT / "Stacky" / "auth" / "ado_auth.json",
    ]
    for p in candidates:
        token = _read_pat_file(p)
        if token:
            return f"Basic {token}"

    raise AdoConfigError(
        "ADO PAT no encontrado. Setea ADO_PAT en backend/.env o llena Tools/PAT-ADO."
    )


class AdoClient:
    def __init__(self, org: str | None = None, project: str | None = None):
        self.org = (org or config.ADO_ORG or "UbimiaPacifico").strip()
        self.project = (project or config.ADO_PROJECT or "Strategist_Pacifico").strip()
        if not self.org or not self.project:
            raise AdoConfigError("ADO_ORG y ADO_PROJECT son obligatorios.")
        self._auth = _resolve_auth_header()
        self._base_proj = (
            f"https://dev.azure.com/{urllib.parse.quote(self.org)}/"
            f"{urllib.parse.quote(self.project)}"
        )

    def _headers(self, content_type: str = "application/json") -> dict[str, str]:
        return {
            "Authorization": self._auth,
            "Content-Type": content_type,
            "Accept": "application/json",
        }

    def _request(self, method: str, url: str, body: dict | list | None = None) -> dict:
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            raise AdoApiError(f"ADO {method} {url} → {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise AdoApiError(f"ADO network error {method} {url}: {e.reason}") from e

    def fetch_open_work_items(self, wiql: str | None = None) -> list[dict]:
        ids = self._wiql_ids(wiql or _DEFAULT_WIQL)
        if not ids:
            return []
        return self._batch_get(ids)

    def _wiql_ids(self, wiql: str) -> list[int]:
        url = f"{self._base_proj}/_apis/wit/wiql?api-version={_API_VERSION}"
        result = self._request("POST", url, {"query": wiql})
        return [int(w["id"]) for w in (result.get("workItems") or []) if w.get("id") is not None]

    def _batch_get(self, ids: list[int], page: int = 200) -> list[dict]:
        out: list[dict] = []
        fields = [
            "System.Id",
            "System.Title",
            "System.State",
            "System.Description",
            "System.WorkItemType",
            "System.AssignedTo",
            "System.ChangedDate",
            "Microsoft.VSTS.Common.Priority",
        ]
        fields_qs = ",".join(fields)
        for i in range(0, len(ids), page):
            chunk = ids[i : i + page]
            ids_qs = ",".join(str(x) for x in chunk)
            url = (
                f"{self._base_proj}/_apis/wit/workitems"
                f"?ids={ids_qs}&fields={urllib.parse.quote(fields_qs)}"
                f"&api-version={_API_VERSION}"
            )
            data = self._request("GET", url)
            out.extend(data.get("value") or [])
        return out

    def work_item_url(self, ado_id: int) -> str:
        return f"{self._base_proj}/_workitems/edit/{ado_id}"
