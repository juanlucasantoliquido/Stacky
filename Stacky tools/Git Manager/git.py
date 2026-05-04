#!/usr/bin/env python3
"""
git.py — Gestor de repositorios Git (Azure DevOps) via CLI
Sin servidor, sin dependencias externas — solo Python 3.8+ stdlib.

ACCIONES:
  repos        Lista repositorios del proyecto
  branches     Lista branches de un repositorio
  pr list      Lista pull requests
  pr get       Obtiene detalle de un PR
  pr create    Crea un pull request
  pr update    Actualiza título/descripción/estado de un PR
  pr abandon   Abandona un PR
  identity     Busca un usuario por email/nombre (para obtener GUIDs de reviewers)

SALIDA: siempre JSON a stdout
ERRORES: JSON a stdout con "ok": false  +  exit code 1

CONFIGURACIÓN (en orden de prioridad):
  1. Args CLI:  --org  --project  --repo  --pat
  2. git-config.json en la misma carpeta que este script
  3. ../../PAT-ADO  (compatibilidad con Stacky Agents)

EJEMPLOS:
  python git.py repos
  python git.py branches --repo Strategist_Pacifico
  python git.py branches --repo Strategist_Pacifico --filter feature
  python git.py pr list --repo Strategist_Pacifico
  python git.py pr list --repo Strategist_Pacifico --status completed
  python git.py pr get 42 --repo Strategist_Pacifico
  python git.py pr create --repo Strategist_Pacifico --source feature/login --target main --title "Agrega login SSO"
  python git.py pr create --repo Strategist_Pacifico --source feature/login --target main --title "PR" --desc "Detalle" --reviewer guid1 guid2 --draft
  python git.py pr create --repo Strategist_Pacifico --source feature/login --target main --title "PR" --work-items 1234 5678
  python git.py pr update 42 --repo Strategist_Pacifico --title "Nuevo titulo"
  python git.py pr update 42 --repo Strategist_Pacifico --publish
  python git.py pr abandon 42 --repo Strategist_Pacifico
  python git.py identity --search "juan.perez@empresa.com"
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# ─── CONFIG ──────────────────────────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).resolve().parent
_API_VER = "7.1"
_TIMEOUT = 30
_B64_RE = re.compile(r"^[A-Za-z0-9+/=]+$")


def _load_config() -> dict:
    """Lee git-config.json → fallback PAT-ADO → dict vacío."""
    cfg_file = _SCRIPT_DIR / "git-config.json"
    if cfg_file.is_file():
        try:
            return json.loads(cfg_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    # Busca PAT-ADO en niveles superiores (compatibilidad Stacky)
    for rel in ("../PAT-ADO", "../../PAT-ADO", "../../../PAT-ADO"):
        pat_file = (_SCRIPT_DIR / rel).resolve()
        if pat_file.is_file():
            try:
                data = json.loads(pat_file.read_text(encoding="utf-8"))
                return {
                    "pat": data.get("pat", ""),
                    "pat_format": data.get("pat_format", ""),
                }
            except Exception:
                pass
    return {}


def _resolve(args_ns: argparse.Namespace) -> tuple[str, str, str, str]:
    """Resuelve org / project / repo / pat: CLI args > git-config.json > PAT-ADO."""
    cfg = _load_config()
    org = (getattr(args_ns, "org", None) or cfg.get("org", "") or "").strip()
    project = (getattr(args_ns, "project", None) or cfg.get("project", "") or "").strip()
    repo = (getattr(args_ns, "repo", None) or cfg.get("repo", "") or "").strip()
    pat_raw = (getattr(args_ns, "pat", None) or cfg.get("pat", "") or "").strip()
    pat_fmt = cfg.get("pat_format", "").strip().lower()
    return org, project, repo, _encode_pat(pat_raw, pat_fmt)


def _looks_preencoded(s: str) -> bool:
    return len(s) >= 80 and bool(_B64_RE.match(s))


def _encode_pat(raw: str, fmt: str = "") -> str:
    if not raw:
        return ""
    if fmt == "preencoded" or _looks_preencoded(raw):
        return raw
    return base64.b64encode(f":{raw}".encode()).decode("ascii")


# ─── CLIENTE ─────────────────────────────────────────────────────────────────

class GitError(RuntimeError):
    def __init__(self, msg: str, status: int = 0):
        super().__init__(msg)
        self.status = status


class GitClient:
    def __init__(self, org: str, project: str, pat_encoded: str):
        if not org or not project:
            raise GitError(
                "org y project son obligatorios. Revisa git-config.json."
            )
        if not pat_encoded:
            raise GitError(
                "PAT no encontrado.\n"
                "Crea 'git-config.json' en la carpeta de git.py con:\n"
                '  { "org": "...", "project": "...", "repo": "...", "pat": "tu-PAT-aqui" }'
            )
        self.org = org
        self.project = project
        self._auth = f"Basic {pat_encoded}"
        self._base = f"https://dev.azure.com/{urllib.parse.quote(org)}"
        self._proj = f"{self._base}/{urllib.parse.quote(project)}"
        self._vssps = f"https://vssps.dev.azure.com/{urllib.parse.quote(org)}"

    def _req(
        self,
        method: str,
        url: str,
        body: Any = None,
        ct: str = "application/json",
    ) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": self._auth,
                "Content-Type": ct,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
                raw = r.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")[:800]
            except Exception:
                pass
            raise GitError(f"HTTP {e.code} {method} {url}\n{detail}", e.code) from e
        except urllib.error.URLError as e:
            raise GitError(f"Error de red: {e.reason}") from e

    # ── REPOS ─────────────────────────────────────────────────────────────────

    def list_repos(self) -> list[dict]:
        url = f"{self._proj}/_apis/git/repositories?api-version={_API_VER}"
        r = self._req("GET", url)
        return [
            {
                "id": repo["id"],
                "name": repo["name"],
                "default_branch": repo.get("defaultBranch", "").replace("refs/heads/", ""),
                "url": repo.get("remoteUrl", ""),
                "size_kb": repo.get("size", 0),
            }
            for repo in (r.get("value") or [])
        ]

    # ── BRANCHES ──────────────────────────────────────────────────────────────

    def list_branches(self, repo: str, filter_text: str = "") -> list[dict]:
        repo_enc = urllib.parse.quote(repo)
        url = (
            f"{self._proj}/_apis/git/repositories/{repo_enc}/refs"
            f"?filter=heads/&api-version={_API_VER}"
        )
        if filter_text:
            url += f"&filterContains={urllib.parse.quote(filter_text)}"
        r = self._req("GET", url)
        return [
            {
                "name": ref["name"].replace("refs/heads/", ""),
                "full_ref": ref["name"],
                "commit": ref.get("objectId", ""),
                "creator": (ref.get("creator") or {}).get("displayName", ""),
            }
            for ref in (r.get("value") or [])
        ]

    # ── PULL REQUESTS ─────────────────────────────────────────────────────────

    def list_prs(
        self,
        repo: str,
        status: str = "active",
        source_branch: str = "",
        target_branch: str = "",
        limit: int = 100,
    ) -> list[dict]:
        repo_enc = urllib.parse.quote(repo)
        qs_parts = [
            f"searchCriteria.status={urllib.parse.quote(status)}",
            f"$top={limit}",
            f"api-version={_API_VER}",
        ]
        if source_branch:
            qs_parts.append(
                f"searchCriteria.sourceRefName={urllib.parse.quote('refs/heads/' + source_branch)}"
            )
        if target_branch:
            qs_parts.append(
                f"searchCriteria.targetRefName={urllib.parse.quote('refs/heads/' + target_branch)}"
            )
        url = (
            f"{self._proj}/_apis/git/repositories/{repo_enc}/pullrequests"
            f"?{'&'.join(qs_parts)}"
        )
        r = self._req("GET", url)
        return [self._pr_dict(pr) for pr in (r.get("value") or [])]

    def get_pr(self, repo: str, pr_id: int) -> dict:
        repo_enc = urllib.parse.quote(repo)
        url = (
            f"{self._proj}/_apis/git/repositories/{repo_enc}/pullrequests/{pr_id}"
            f"?api-version={_API_VER}"
        )
        return self._pr_dict(self._req("GET", url))

    def create_pr(
        self,
        repo: str,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str = "",
        reviewers: list[str] | None = None,
        work_item_ids: list[int] | None = None,
        is_draft: bool = False,
        auto_complete: bool = False,
    ) -> dict:
        repo_enc = urllib.parse.quote(repo)
        body: dict[str, Any] = {
            "title": title,
            "description": description,
            "sourceRefName": f"refs/heads/{source_branch}",
            "targetRefName": f"refs/heads/{target_branch}",
            "isDraft": is_draft,
        }
        if reviewers:
            body["reviewers"] = [{"id": rv} for rv in reviewers]
        if work_item_ids:
            body["workItemRefs"] = [{"id": str(wi)} for wi in work_item_ids]
        if auto_complete:
            body["completionOptions"] = {
                "mergeStrategy": "squash",
                "deleteSourceBranch": False,
            }
        url = (
            f"{self._proj}/_apis/git/repositories/{repo_enc}/pullrequests"
            f"?api-version={_API_VER}"
        )
        return self._pr_dict(self._req("POST", url, body))

    def update_pr(
        self,
        repo: str,
        pr_id: int,
        title: str = "",
        description: str = "",
        status: str = "",
        is_draft: bool | None = None,
    ) -> dict:
        repo_enc = urllib.parse.quote(repo)
        body: dict[str, Any] = {}
        if title:
            body["title"] = title
        if description:
            body["description"] = description
        if status:
            body["status"] = status
        if is_draft is not None:
            body["isDraft"] = is_draft
        if not body:
            raise GitError(
                "Debes especificar al menos un campo para actualizar "
                "(--title, --desc, --publish)."
            )
        url = (
            f"{self._proj}/_apis/git/repositories/{repo_enc}/pullrequests/{pr_id}"
            f"?api-version={_API_VER}"
        )
        return self._pr_dict(self._req("PATCH", url, body))

    def abandon_pr(self, repo: str, pr_id: int) -> dict:
        return self.update_pr(repo, pr_id, status="abandoned")

    # ── IDENTITY ──────────────────────────────────────────────────────────────

    def search_identity(self, search: str) -> list[dict]:
        url = (
            f"{self._vssps}/_apis/identities"
            f"?searchFilter=General"
            f"&filterValue={urllib.parse.quote(search)}"
            f"&queryMembership=None"
            f"&api-version=6.0"
        )
        r = self._req("GET", url)
        results = []
        for ident in r.get("value") or []:
            props = ident.get("properties") or {}
            account_prop = props.get("Account") or {}
            results.append(
                {
                    "id": ident.get("id", ""),
                    "display_name": ident.get("providerDisplayName", ""),
                    "unique_name": (
                        account_prop.get("$value", "")
                        if isinstance(account_prop, dict)
                        else ""
                    ),
                    "descriptor": ident.get("subjectDescriptor", ""),
                }
            )
        return results

    # ── Serialización ─────────────────────────────────────────────────────────

    def _pr_dict(self, pr: dict) -> dict:
        created_by = pr.get("createdBy") or {}
        repo_info = pr.get("repository") or {}
        last_merge = pr.get("lastMergeCommit") or {}
        return {
            "id": pr.get("pullRequestId"),
            "title": pr.get("title", ""),
            "description": pr.get("description", ""),
            "status": pr.get("status", ""),
            "is_draft": pr.get("isDraft", False),
            "source_branch": pr.get("sourceRefName", "").replace("refs/heads/", ""),
            "target_branch": pr.get("targetRefName", "").replace("refs/heads/", ""),
            "created_by": created_by.get("displayName", ""),
            "created_date": pr.get("creationDate"),
            "closed_date": pr.get("closedDate"),
            "reviewers": [
                {
                    "id": rv.get("id", ""),
                    "display_name": rv.get("displayName", ""),
                    "vote": rv.get("vote", 0),
                    "vote_label": _vote_label(rv.get("vote", 0)),
                }
                for rv in (pr.get("reviewers") or [])
            ],
            "merge_status": pr.get("mergeStatus", ""),
            "merge_commit": last_merge.get("commitId", ""),
            "repo": repo_info.get("name", ""),
            "url": (
                f"https://dev.azure.com/{self.org}/{self.project}"
                f"/_git/{repo_info.get('name', '')}/"
                f"pullrequest/{pr.get('pullRequestId', '')}"
            ),
        }


def _vote_label(vote: int) -> str:
    return {
        10: "approved",
        5: "approved_with_suggestions",
        0: "no_vote",
        -5: "waiting_for_author",
        -10: "rejected",
    }.get(vote, "unknown")


# ─── OUTPUT ──────────────────────────────────────────────────────────────────

def _ok(action: str, result: Any, **extra) -> None:
    print(
        json.dumps(
            {"ok": True, "action": action, "result": result, **extra},
            ensure_ascii=False,
            indent=2,
        )
    )


def _err(action: str, message: str, error_type: str = "error") -> None:
    print(
        json.dumps(
            {"ok": False, "action": action, "error": error_type, "message": message},
            ensure_ascii=False,
            indent=2,
        )
    )
    sys.exit(1)


# ─── PARSER ──────────────────────────────────────────────────────────────────

def _add_creds(p: argparse.ArgumentParser) -> None:
    """Agrega --org, --project, --pat opcionales (override de git-config.json)."""
    g = p.add_argument_group("credenciales (override de git-config.json)")
    g.add_argument("--org",     metavar="ORG",     help="Organización ADO")
    g.add_argument("--project", metavar="PROJECT", help="Proyecto ADO")
    g.add_argument("--pat",     metavar="PAT",     help="Personal Access Token")


def _add_repo_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--repo",
        metavar="REPO",
        help="Nombre del repositorio (override de git-config.json)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python git.py",
        description="Gestor de repos Git en Azure DevOps. Salida: siempre JSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EJEMPLOS:
  python git.py repos
  python git.py branches --repo Strategist_Pacifico
  python git.py branches --repo Strategist_Pacifico --filter feature
  python git.py pr list --repo Strategist_Pacifico
  python git.py pr list --repo Strategist_Pacifico --status completed
  python git.py pr list --repo Strategist_Pacifico --source feature/login
  python git.py pr get 42 --repo Strategist_Pacifico
  python git.py pr create --repo Strategist_Pacifico --source feature/login --target main --title "Agrega login SSO"
  python git.py pr create --repo Strategist_Pacifico --source feature/login --target main --title "PR" --desc "Detalle"
  python git.py pr create --repo Strategist_Pacifico --source feature/login --target main --title "PR" --reviewer guid1 guid2
  python git.py pr create --repo Strategist_Pacifico --source feature/login --target main --title "PR" --work-items 1234 5678 --draft
  python git.py pr update 42 --repo Strategist_Pacifico --title "Nuevo titulo"
  python git.py pr update 42 --repo Strategist_Pacifico --publish
  python git.py pr abandon 42 --repo Strategist_Pacifico
  python git.py identity --search "juan.perez@empresa.com"
        """,
    )

    sub = parser.add_subparsers(dest="action", metavar="ACCION")
    sub.required = True

    # ── repos ─────────────────────────────────────────────────────────────────
    p_repos = sub.add_parser("repos", help="Lista repositorios del proyecto")
    _add_creds(p_repos)

    # ── branches ──────────────────────────────────────────────────────────────
    p_branches = sub.add_parser("branches", help="Lista branches de un repositorio")
    _add_repo_arg(p_branches)
    p_branches.add_argument(
        "--filter",
        dest="filter_text",
        metavar="TEXTO",
        default="",
        help="Filtrar branches que contengan este texto",
    )
    _add_creds(p_branches)

    # ── pr ────────────────────────────────────────────────────────────────────
    p_pr = sub.add_parser("pr", help="Gestión de Pull Requests")
    pr_sub = p_pr.add_subparsers(dest="pr_action", metavar="PR_ACCION")
    pr_sub.required = True

    # pr list
    p_pr_list = pr_sub.add_parser("list", help="Lista pull requests")
    _add_repo_arg(p_pr_list)
    p_pr_list.add_argument(
        "--status",
        metavar="STATUS",
        default="active",
        choices=["active", "abandoned", "completed", "all"],
        help="Estado del PR: active|abandoned|completed|all (default: active)",
    )
    p_pr_list.add_argument("--source", metavar="BRANCH", default="", help="Filtrar por branch origen")
    p_pr_list.add_argument("--target", metavar="BRANCH", default="", help="Filtrar por branch destino")
    p_pr_list.add_argument("--limit",  metavar="N", type=int, default=100, help="Máximo de resultados (default: 100)")
    _add_creds(p_pr_list)

    # pr get
    p_pr_get = pr_sub.add_parser("get", help="Obtiene detalle completo de un PR")
    p_pr_get.add_argument("id", type=int, metavar="ID", help="ID del pull request")
    _add_repo_arg(p_pr_get)
    _add_creds(p_pr_get)

    # pr create
    p_pr_create = pr_sub.add_parser("create", help="Crea un pull request")
    _add_repo_arg(p_pr_create)
    p_pr_create.add_argument("--source",   required=True, metavar="BRANCH",
                             help="Branch origen (ej: feature/mi-feature)")
    p_pr_create.add_argument("--target",   required=True, metavar="BRANCH",
                             help="Branch destino (ej: main, develop)")
    p_pr_create.add_argument("--title",    required=True, metavar="TITULO",
                             help="Título del PR")
    p_pr_create.add_argument("--desc",     default="", metavar="TEXTO",
                             help="Descripción del PR (texto plano)")
    p_pr_create.add_argument(
        "--reviewer",
        nargs="*",
        metavar="GUID",
        dest="reviewers",
        default=[],
        help="GUIDs de revisores (obtener con: python git.py identity --search EMAIL)",
    )
    p_pr_create.add_argument(
        "--work-items",
        nargs="*",
        metavar="ID",
        dest="work_items",
        type=int,
        default=[],
        help="IDs de work items ADO a vincular al PR",
    )
    p_pr_create.add_argument("--draft",         action="store_true",
                             help="Crear como borrador (draft)")
    p_pr_create.add_argument("--auto-complete", action="store_true",
                             dest="auto_complete",
                             help="Activar auto-complete al crear el PR")
    _add_creds(p_pr_create)

    # pr update
    p_pr_update = pr_sub.add_parser("update", help="Actualiza un PR existente")
    p_pr_update.add_argument("id", type=int, metavar="ID", help="ID del pull request")
    _add_repo_arg(p_pr_update)
    p_pr_update.add_argument("--title",   metavar="TITULO", default="", help="Nuevo título")
    p_pr_update.add_argument("--desc",    metavar="TEXTO",  default="", help="Nueva descripción")
    p_pr_update.add_argument("--publish", action="store_true",
                             help="Publicar borrador (isDraft: true → false)")
    _add_creds(p_pr_update)

    # pr abandon
    p_pr_abandon = pr_sub.add_parser("abandon", help="Abandona un PR")
    p_pr_abandon.add_argument("id", type=int, metavar="ID", help="ID del pull request")
    _add_repo_arg(p_pr_abandon)
    _add_creds(p_pr_abandon)

    # ── identity ──────────────────────────────────────────────────────────────
    p_identity = sub.add_parser(
        "identity",
        help="Busca usuarios por email/nombre (útil para GUIDs de reviewers)",
    )
    p_identity.add_argument(
        "--search", required=True, metavar="TEXTO",
        help="Email o nombre parcial del usuario a buscar",
    )
    _add_creds(p_identity)

    return parser


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    action = args.action

    try:
        org, project, repo, pat_enc = _resolve(args)
        client = GitClient(org, project, pat_enc)
    except GitError as e:
        _err(action, str(e), "config")
    except Exception as e:
        _err(action, str(e), "config")

    try:
        if action == "repos":
            result = client.list_repos()
            _ok(action, result, count=len(result))

        elif action == "branches":
            if not repo:
                _err(action, "Especifica --repo o define 'repo' en git-config.json.", "config")
            result = client.list_branches(repo, filter_text=args.filter_text)
            _ok(action, result, count=len(result), repo=repo)

        elif action == "pr":
            pr_action = args.pr_action
            full_action = f"pr {pr_action}"

            if pr_action == "list":
                if not repo:
                    _err(full_action, "Especifica --repo o define 'repo' en git-config.json.", "config")
                result = client.list_prs(
                    repo=repo,
                    status=args.status,
                    source_branch=args.source,
                    target_branch=args.target,
                    limit=args.limit,
                )
                _ok(full_action, result, count=len(result), repo=repo, status=args.status)

            elif pr_action == "get":
                if not repo:
                    _err(full_action, "Especifica --repo o define 'repo' en git-config.json.", "config")
                _ok(full_action, client.get_pr(repo, args.id))

            elif pr_action == "create":
                if not repo:
                    _err(full_action, "Especifica --repo o define 'repo' en git-config.json.", "config")
                result = client.create_pr(
                    repo=repo,
                    source_branch=args.source,
                    target_branch=args.target,
                    title=args.title,
                    description=args.desc,
                    reviewers=args.reviewers or [],
                    work_item_ids=args.work_items or [],
                    is_draft=args.draft,
                    auto_complete=args.auto_complete,
                )
                _ok(full_action, result)

            elif pr_action == "update":
                if not repo:
                    _err(full_action, "Especifica --repo o define 'repo' en git-config.json.", "config")
                is_draft: bool | None = False if args.publish else None
                result = client.update_pr(
                    repo=repo,
                    pr_id=args.id,
                    title=args.title,
                    description=args.desc,
                    is_draft=is_draft,
                )
                _ok(full_action, result)

            elif pr_action == "abandon":
                if not repo:
                    _err(full_action, "Especifica --repo o define 'repo' en git-config.json.", "config")
                _ok(full_action, client.abandon_pr(repo, args.id))

        elif action == "identity":
            result = client.search_identity(args.search)
            _ok(action, result, count=len(result))

    except GitError as e:
        err_type = f"http_{e.status}" if e.status else "error"
        _err(action, str(e), err_type)
    except Exception as e:
        _err(action, str(e))


if __name__ == "__main__":
    main()
