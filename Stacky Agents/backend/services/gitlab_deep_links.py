"""
services/gitlab_deep_links.py — Compositoras PURAS de deep links GitLab (Plan 75).

Contrato de encoding (C3 CRÍTICO):
  - project_path_encoded se recibe YA URL-encoded (output de _project_path() de
    gitlab_client.py:98 que ya encodea '/' a '%2F').
    Se usa DIRECTAMENTE sin pasar por _enc().
  - _enc() solo se aplica sobre: iid, sha, group y query (que llegan sin encodear).
  - NUNCA aplicar _enc() sobre project_path_encoded → produciría %25 (doble-encoding)
    y 404 en GitLab para subgroups.

Fases:
  F1 — Compositoras PURAS (5 funciones + helpers)
  F3 — Fallback Free para épicas + resolve_epic_deep_link
  F5 — Composición bidireccional (epic_related_links, pipeline_trigger_issue_link)
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Optional


# ── F1: Compositoras PURAS ────────────────────────────────────────────────────

def _norm_base(base_url: str) -> str:
    """rstrip '/' del base_url (defensivo)."""
    return (base_url or "").rstrip("/")


def _enc(value: str) -> str:
    """URL-encode un segmento NO pre-encoded (iid, sha, group, query strings).

    NUNCA aplicar sobre project_path que ya viene de _project_path() (ya encoded)."""
    return urllib.parse.quote(str(value), safe="")


def compose_issue_url(base_url: str, project_path_encoded: str, iid: str) -> str:
    """Compone URL de issue GitLab.

    project_path_encoded: string ya URL-encoded (output de _project_path()).
    iid: string sin encodear (se encodea aquí).
    """
    return f"{_norm_base(base_url)}/{project_path_encoded}/-/issues/{_enc(iid)}"


def compose_mr_url(base_url: str, project_path_encoded: str, iid: str) -> str:
    """Compone URL de merge request GitLab.

    project_path_encoded: string ya URL-encoded.
    iid: string sin encodear.
    """
    return f"{_norm_base(base_url)}/{project_path_encoded}/-/merge_requests/{_enc(iid)}"


def compose_commit_url(base_url: str, project_path_encoded: str, sha: str) -> str:
    """Compone URL de commit GitLab.

    project_path_encoded: string ya URL-encoded.
    sha: string sin encodear (URL-safe pero se encodea defensivamente).
    """
    return f"{_norm_base(base_url)}/{project_path_encoded}/-/commit/{_enc(sha)}"


def compose_epic_url(base_url: str, group: str, iid: str) -> str:
    """Compone URL de épica GitLab (Premium/Ultimate).

    group: string sin encodear (se encodea aquí).
    iid: string sin encodear.
    """
    return f"{_norm_base(base_url)}/groups/{_enc(group)}/-/epics/{_enc(iid)}"


def pipeline_web_url(pipeline: Optional[dict]) -> Optional[str]:
    """Selector puro: retorna pipeline['web_url'] si viene del API, sino None."""
    return (pipeline or {}).get("web_url") or None


# ── F3: Fallback Free para épicas ─────────────────────────────────────────────

def compose_search_url(base_url: str, project_path_encoded: str, query: str) -> str:
    """Compone URL de búsqueda de issues con label en GitLab.

    Produce: {base}/{project_path_encoded}/-/issues?search=...&label_name=...
    para la heurística de búsqueda de épicas en GitLab Free.
    """
    # Para el query de label type::epic, separamos label_name del search
    label = None
    search = query
    if query.startswith("label:"):
        label = query[len("label:"):]
        search = ""
    base = _norm_base(base_url)
    params: dict[str, str] = {}
    if search:
        params["search"] = search
    if label:
        params["label_name[]"] = label
    qs = urllib.parse.urlencode(params) if params else ""
    url = f"{base}/{project_path_encoded}/-/issues"
    return f"{url}?{qs}" if qs else url


def resolve_epic_deep_link(
    *,
    dest_provider,
    epic_strategy: str,
    gitlab_iid: str,
    fallback_issue_iid: Optional[str],
) -> str:
    """Estrategia de fallback Free para deep links de épicas.

    Atributos de dest_provider que se leen (C4 — documentados con su origen):
      - dest_provider._group: str | None — grupo GitLab para épicas Premium
        (gitlab_provider.py, atributo _group inicializado en __init__).
        Si es None o string vacío, el proyecto es Free/no-configurado.
      - dest_provider._epics_native: bool — flag de tier (gitlab_provider.py:39).
        True si el GitLab es Premium con épicas nativas; False si Free.
      - dest_provider._client._base_url: str — base del servidor (gitlab_client.py:56).
      - dest_provider._client._project_path(): str — path ya URL-encoded
        (gitlab_client.py:98).

    Lógica:
      - epic_strategy == 'premium_native' y provider tiene _group
        → compose_epic_url(base, group, iid).
      - epic_strategy == 'free_degrade' o sin _group
        → compose_issue_url(project_path_encoded, fallback_issue_iid).
      - Sin fallback_issue_iid
        → compose_search_url(base_url, project_path_encoded, 'label:type::epic').
      - epic_strategy == 'auto'
        → detecta _epics_native para decidir entre premium_native y free_degrade.

    Nunca escribe; solo compone.
    """
    base_url = dest_provider._client._base_url
    project_path_encoded = dest_provider._client._project_path()
    group = getattr(dest_provider, "_group", "") or ""
    epics_native = getattr(dest_provider, "_epics_native", False)

    # Resolver estrategia 'auto'
    resolved_strategy = epic_strategy
    if epic_strategy == "auto":
        resolved_strategy = "premium_native" if epics_native else "free_degrade"

    if resolved_strategy == "premium_native" and group:
        return compose_epic_url(base_url, group, gitlab_iid)

    # free_degrade: apunta al issue degradado si hay iid, sino búsqueda por label
    if fallback_issue_iid:
        return compose_issue_url(base_url, project_path_encoded, fallback_issue_iid)

    return compose_search_url(base_url, project_path_encoded, "label:type::epic")


# ── F5: Composición bidireccional ─────────────────────────────────────────────

def epic_related_links(
    *,
    dest_provider,
    epic_iid: str,
    child_issues: list[dict],
    mrs: list[dict],
    pipelines: list[dict],
) -> dict:
    """Compone URLs para los recursos relacionados a una épica.

    Retorna {issue_urls: [...], mr_urls: [...], pipeline_urls: [...]}.
    No escribe; solo compone a partir de los IDs que el caller ya recolectó.
    """
    issue_urls = []
    for issue in child_issues or []:
        iid = str(issue.get("iid") or issue.get("id") or "")
        if iid:
            url = dest_provider.item_url(iid)
            if url:
                issue_urls.append(url)

    mr_urls = []
    for mr in mrs or []:
        iid = str(mr.get("iid") or mr.get("id") or "")
        if iid and hasattr(dest_provider, "mr_url"):
            url = dest_provider.mr_url(iid)
            if url:
                mr_urls.append(url)

    pipeline_urls = []
    for pipeline in pipelines or []:
        url = pipeline_web_url(pipeline)
        if url:
            pipeline_urls.append(url)

    return {"issue_urls": issue_urls, "mr_urls": mr_urls, "pipeline_urls": pipeline_urls}


# Regex documentada (C5): patrón EXACTO de rama disparada por issue.
# Matches: "issue-42", "issue-42-fix-auth" (NO: "release-42", "feat/42-dashboard", "my-issue-42").
_ISSUE_TRIGGER_RE = re.compile(r"^issue-(\d+)(?:-|$)")


def pipeline_trigger_issue_link(pipeline: Optional[dict], *, dest_provider) -> Optional[str]:
    """Si el pipeline tiene ref que sigue el patrón ^issue-(\\d+)(?:-|$),
    compone el link al issue. Heurística determinista documentada.

    Ejemplos:
      ref='issue-42'           -> URL issue 42
      ref='issue-42-fix-auth'  -> URL issue 42
      ref='release-42'         -> None  (no match: 'release' no es 'issue')
      ref='main'               -> None
      ref='feat/42-dashboard'  -> None (no empieza con 'issue-')
      ref='my-issue-42'        -> None (no empieza con 'issue-')
    """
    ref = (pipeline or {}).get("ref") or ""
    m = _ISSUE_TRIGGER_RE.match(ref)
    if not m:
        return None
    return dest_provider.item_url(m.group(1))
