#!/usr/bin/env python3
"""
ado.py — Gestor de tickets Azure DevOps via CLI
Sin servidor, sin dependencias externas — solo Python 3.8+ stdlib.

ACCIONES:
  list      Lista tickets del proyecto
  get       Obtiene detalle completo de un ticket
  create    Crea un nuevo ticket
  comment   Agrega un comentario (HTML o texto plano)
  state     Cambia el estado de un ticket
  comments  Lista los comentarios de un ticket
  states    Lista los estados disponibles
  types     Lista los tipos de work item disponibles

SALIDA: siempre JSON a stdout
ERRORES: JSON a stdout con "ok": false  +  exit code 1

CONFIGURACIÓN (en orden de prioridad):
  1. Args CLI:  --org  --project  --pat
  2. ado-config.json en la misma carpeta que este script
  3. ../PAT-ADO  (compatibilidad con Stacky Agents)

EJEMPLOS:
  python ado.py list
  python ado.py list --state "Technical review"
  python ado.py get 1234
  python ado.py create --title "Arreglar validacion X" --desc "El campo Y no valida nulos"
  python ado.py create --title "Titulo" --desc "<h2>HTML</h2>" --html
  python ado.py comment 1234 --text "Analisis completado"
  python ado.py comment 1234 --text "<b>Listo</b>" --html
  python ado.py state 1234 "To Do"
  python ado.py comments 1234
  python ado.py states
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
    """Lee ado-config.json → fallback ../PAT-ADO → dict vacío."""
    # 1. ado-config.json junto al script
    cfg = _SCRIPT_DIR / "ado-config.json"
    if cfg.is_file():
        try:
            return json.loads(cfg.read_text(encoding="utf-8"))
        except Exception:
            pass
    # 2. ../PAT-ADO (compatibilidad Stacky)
    pat_file = _SCRIPT_DIR.parent / "PAT-ADO"
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


def _resolve(args_ns: argparse.Namespace) -> tuple[str, str, str]:
    """Resuelve org/project/pat: CLI args > ado-config.json > PAT-ADO."""
    cfg = _load_config()
    org = (
        getattr(args_ns, "org", None)
        or cfg.get("org", "")
        or "UbimiaPacifico"
    ).strip()
    project = (
        getattr(args_ns, "project", None)
        or cfg.get("project", "")
        or "Strategist_Pacifico"
    ).strip()
    pat_raw = (
        getattr(args_ns, "pat", None)
        or cfg.get("pat", "")
        or ""
    ).strip()
    pat_fmt = cfg.get("pat_format", "").strip().lower()
    return org, project, _encode_pat(pat_raw, pat_fmt)


def _looks_preencoded(s: str) -> bool:
    return len(s) >= 80 and bool(_B64_RE.match(s))


def _encode_pat(raw: str, fmt: str = "") -> str:
    if not raw:
        return ""
    if fmt == "preencoded" or _looks_preencoded(raw):
        return raw
    return base64.b64encode(f":{raw}".encode()).decode("ascii")


# ─── CLIENTE ADO ─────────────────────────────────────────────────────────────

class AdoError(RuntimeError):
    def __init__(self, msg: str, status: int = 0):
        super().__init__(msg)
        self.status = status


def _plain_to_html(text: str) -> str:
    """Texto plano → HTML simple para ADO (preserva saltos de línea)."""
    esc = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return "".join(
        f"<p>{l if l.strip() else '&nbsp;'}</p>"
        for l in esc.split("\n")
    )


def _ensure_html(content: str, is_html: bool) -> str:
    if is_html:
        s = content.strip()
        return s if re.match(r"^<[a-zA-Z]", s) else f"<div>{s}</div>"
    return _plain_to_html(content)


class AdoClient:
    def __init__(self, org: str, project: str, pat_encoded: str):
        if not org or not project:
            raise AdoError("org y project son obligatorios. Revisa ado-config.json.")
        if not pat_encoded:
            raise AdoError(
                "PAT no encontrado.\n"
                "Crea 'ado-config.json' en la carpeta de ado.py con:\n"
                '  { "org": "...", "project": "...", "pat": "tu-PAT-aqui" }'
            )
        self.org = org
        self.project = project
        self._auth = f"Basic {pat_encoded}"
        self._base = f"https://dev.azure.com/{urllib.parse.quote(org)}"
        self._proj_url = f"{self._base}/{urllib.parse.quote(project)}"

    def _req(self, method: str, url: str, body: Any = None,
             ct: str = "application/json") -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url, data=data, method=method,
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
                detail = e.read().decode("utf-8", errors="replace")[:600]
            except Exception:
                pass
            raise AdoError(f"HTTP {e.code} {method} {url}\n{detail}", e.code) from e
        except urllib.error.URLError as e:
            raise AdoError(f"Error de red: {e.reason}") from e

    # ── WIQL ─────────────────────────────────────────────────────────────────
    def _wiql_ids(self, wiql: str) -> list[int]:
        url = f"{self._proj_url}/_apis/wit/wiql?api-version={_API_VER}"
        r = self._req("POST", url, {"query": wiql})
        return [int(w["id"]) for w in (r.get("workItems") or []) if w.get("id")]

    def _batch_get(self, ids: list[int]) -> list[dict]:
        if not ids:
            return []
        out: list[dict] = []
        fields = [
            "System.Id", "System.Title", "System.State",
            "System.Description", "System.WorkItemType",
            "System.AssignedTo", "System.ChangedDate",
            "System.CreatedDate", "Microsoft.VSTS.Common.Priority",
            "System.AreaPath", "System.Tags",
        ]
        fqs = urllib.parse.quote(",".join(fields))
        for i in range(0, len(ids), 200):
            chunk = ids[i: i + 200]
            ids_qs = ",".join(str(x) for x in chunk)
            url = (
                f"{self._proj_url}/_apis/wit/workitems"
                f"?ids={ids_qs}&fields={fqs}&api-version={_API_VER}"
            )
            out.extend(self._req("GET", url).get("value") or [])
        return out

    # ── ACCIONES ──────────────────────────────────────────────────────────────
    def list_work_items(
        self,
        state: str = "",
        search: str = "",
        limit: int = 200,
        include_closed: bool = False,
    ) -> list[dict]:
        conds = ["[System.TeamProject] = @project"]
        if state:
            conds.append(f"[System.State] = '{state}'")
        elif not include_closed:
            conds.append(
                "[System.State] NOT IN ('Closed','Done','Removed','Completed')"
            )
        wiql = (
            f"SELECT [System.Id] FROM WorkItems "
            f"WHERE {' AND '.join(conds)} "
            f"ORDER BY [System.ChangedDate] DESC"
        )
        ids = self._wiql_ids(wiql)[:limit]
        items = self._batch_get(ids)
        if search:
            s = search.lower()
            items = [
                i for i in items
                if s in str(i.get("fields", {}).get("System.Title", "")).lower()
                or s in str(i.get("id", ""))
            ]
        return [self._wi_dict(i) for i in items]

    def get_work_item(self, wi_id: int) -> dict:
        url = (
            f"{self._proj_url}/_apis/wit/workitems/{wi_id}"
            f"?$expand=all&api-version={_API_VER}"
        )
        return self._wi_dict(self._req("GET", url))

    def create_work_item(
        self,
        title: str,
        description: str = "",
        wi_type: str = "Task",
        priority: int = 2,
        area_path: str = "",
        assigned_to: str = "",
        tags: str = "",
        is_html: bool = False,
    ) -> dict:
        ops: list[dict] = [
            {"op": "add", "path": "/fields/System.Title", "value": title},
            {"op": "add", "path": "/fields/System.Description",
             "value": _ensure_html(description, is_html)},
            {"op": "add", "path": "/fields/Microsoft.VSTS.Common.Priority",
             "value": priority},
        ]
        if area_path:
            ops.append({"op": "add", "path": "/fields/System.AreaPath", "value": area_path})
        if assigned_to:
            ops.append({"op": "add", "path": "/fields/System.AssignedTo", "value": assigned_to})
        if tags:
            ops.append({"op": "add", "path": "/fields/System.Tags", "value": tags})
        url = (
            f"{self._proj_url}/_apis/wit/workitems/"
            f"${urllib.parse.quote(wi_type)}?api-version={_API_VER}"
        )
        return self._wi_dict(
            self._req("POST", url, ops, ct="application/json-patch+json")
        )

    def update_state(self, wi_id: int, state: str) -> dict:
        ops = [{"op": "add", "path": "/fields/System.State", "value": state}]
        url = f"{self._proj_url}/_apis/wit/workitems/{wi_id}?api-version={_API_VER}"
        return self._wi_dict(
            self._req("PATCH", url, ops, ct="application/json-patch+json")
        )

    def add_comment(self, wi_id: int, text: str, is_html: bool = False) -> dict:
        url = (
            f"{self._proj_url}/_apis/wit/workitems/{wi_id}/comments"
            f"?api-version={_API_VER}-preview.3"
        )
        cm = self._req("POST", url, {"text": _ensure_html(text, is_html)})
        return self._comment_dict(cm)

    def list_comments(self, wi_id: int) -> list[dict]:
        url = (
            f"{self._proj_url}/_apis/wit/workitems/{wi_id}/comments"
            f"?api-version={_API_VER}-preview.3"
        )
        return [self._comment_dict(c) for c in self._req("GET", url).get("comments") or []]

    def get_states(self) -> list[str]:
        return [
            "New", "Active", "To Do", "In Progress",
            "Technical review", "Code Review", "Testing",
            "Blocked", "Done", "Closed",
        ]

    def get_types(self) -> list[str]:
        try:
            url = f"{self._proj_url}/_apis/wit/workitemtypes?api-version={_API_VER}"
            r = self._req("GET", url)
            return [t["name"] for t in (r.get("value") or [])]
        except Exception:
            return ["Task", "Bug", "User Story", "Feature", "Epic"]

    # ── Serialización ─────────────────────────────────────────────────────────
    def _wi_dict(self, wi: dict) -> dict:
        f = wi.get("fields") or {}
        assigned = f.get("System.AssignedTo") or {}
        assigned_name = (
            assigned.get("displayName", "") if isinstance(assigned, dict) else str(assigned)
        )
        ado_id = wi.get("id")
        return {
            "id": ado_id,
            "title": f.get("System.Title", ""),
            "state": f.get("System.State", ""),
            "type": f.get("System.WorkItemType", ""),
            "description": f.get("System.Description", ""),
            "priority": f.get("Microsoft.VSTS.Common.Priority"),
            "assigned_to": assigned_name,
            "area_path": f.get("System.AreaPath", ""),
            "tags": f.get("System.Tags", ""),
            "changed_date": f.get("System.ChangedDate"),
            "created_date": f.get("System.CreatedDate"),
            "url": f"{self._proj_url}/_workitems/edit/{ado_id}",
        }

    def _comment_dict(self, c: dict) -> dict:
        author = c.get("createdBy") or {}
        return {
            "id": c.get("id"),
            "text": c.get("text", ""),
            "author": author.get("displayName", "") if isinstance(author, dict) else str(author),
            "created_date": c.get("createdDate"),
            "modified_date": c.get("modifiedDate"),
        }


# ─── OUTPUT ──────────────────────────────────────────────────────────────────

def _ok(action: str, result: Any, **extra) -> None:
    print(json.dumps({"ok": True, "action": action, "result": result, **extra},
                     ensure_ascii=False, indent=2))


def _err(action: str, message: str, error_type: str = "error") -> None:
    print(json.dumps({"ok": False, "action": action,
                      "error": error_type, "message": message},
                     ensure_ascii=False, indent=2))
    sys.exit(1)


# ─── PARSER ──────────────────────────────────────────────────────────────────

def _add_creds(p: argparse.ArgumentParser) -> None:
    """Agrega --org, --project, --pat opcionales (override del ado-config.json)."""
    g = p.add_argument_group("credenciales (override de ado-config.json)")
    g.add_argument("--org",     metavar="ORG",     help="Organización ADO")
    g.add_argument("--project", metavar="PROJECT", help="Proyecto ADO")
    g.add_argument("--pat",     metavar="PAT",     help="Personal Access Token")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python ado.py",
        description="Gestor de tickets Azure DevOps. Salida: siempre JSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EJEMPLOS:
  python ado.py list
  python ado.py list --state "Technical review"
  python ado.py list --search "factura" --limit 50
  python ado.py get 1234
  python ado.py create --title "Bug en login" --desc "El formulario no valida email"
  python ado.py create --title "Titulo" --desc "<h2>HTML</h2><p>Detalle</p>" --html
  python ado.py comment 1234 --text "Analisis completado. Ver seccion 2."
  python ado.py comment 1234 --text "<b>Listo</b>" --html
  python ado.py state 1234 "To Do"
  python ado.py state 1234 "Blocked"
  python ado.py comments 1234
  python ado.py states
  python ado.py types
        """,
    )
    sub = parser.add_subparsers(dest="action", metavar="ACCION")
    sub.required = True

    # ── list ──────────────────────────────────────────────────────────────────
    p_list = sub.add_parser("list", help="Lista tickets del proyecto")
    p_list.add_argument("--state",   metavar="ESTADO", default="",
                        help="Filtrar por estado (ej: 'Technical review')")
    p_list.add_argument("--search",  metavar="TEXTO", default="",
                        help="Filtrar por texto en el título o ID")
    p_list.add_argument("--limit",   metavar="N", type=int, default=200,
                        help="Máximo de resultados (default: 200)")
    p_list.add_argument("--all",     action="store_true",
                        help="Incluir tickets cerrados/completados")
    _add_creds(p_list)

    # ── get ───────────────────────────────────────────────────────────────────
    p_get = sub.add_parser("get", help="Obtiene detalle de un ticket")
    p_get.add_argument("id", type=int, metavar="ID", help="ID del work item")
    _add_creds(p_get)

    # ── create ────────────────────────────────────────────────────────────────
    p_create = sub.add_parser("create", help="Crea un nuevo ticket")
    p_create.add_argument("--title",    required=True,   metavar="TITULO",
                          help="Título del ticket")
    p_create.add_argument("--desc",     default="",      metavar="TEXTO",
                          help="Descripción (texto plano o HTML si usás --html)")
    p_create.add_argument("--html",     action="store_true",
                          help="Indica que --desc es HTML (si no, se trata como texto plano)")
    p_create.add_argument("--type",     default="Task",  metavar="TIPO",
                          help="Tipo de work item: Task|Bug|User Story|Feature|Epic (default: Task)")
    p_create.add_argument("--priority", default=2, type=int, metavar="N",
                          help="Prioridad 1-4 (1=crítica, 4=baja, default: 2)")
    p_create.add_argument("--area",     default="",      metavar="PATH",
                          help="Area path (ej: Strategist_Pacifico\\\\Modulo)")
    p_create.add_argument("--assigned", default="",      metavar="EMAIL",
                          help="Asignar a (email o displayName)")
    p_create.add_argument("--tags",     default="",      metavar="TAGS",
                          help="Tags separados por punto y coma (ej: 'bug; critico')")
    _add_creds(p_create)

    # ── comment ───────────────────────────────────────────────────────────────
    p_comment = sub.add_parser("comment", help="Agrega un comentario a un ticket")
    p_comment.add_argument("id",     type=int, metavar="ID",
                           help="ID del work item")
    p_comment.add_argument("--text", required=True, metavar="TEXTO",
                           help="Texto del comentario (plano o HTML si usás --html)")
    p_comment.add_argument("--html", action="store_true",
                           help="Indica que --text es HTML")
    _add_creds(p_comment)

    # ── state ─────────────────────────────────────────────────────────────────
    p_state = sub.add_parser("state", help="Cambia el estado de un ticket")
    p_state.add_argument("id",    type=int, metavar="ID",
                         help="ID del work item")
    p_state.add_argument("state", metavar="ESTADO",
                         help="Nuevo estado (ej: 'To Do', 'Blocked', 'Done')")
    _add_creds(p_state)

    # ── comments ──────────────────────────────────────────────────────────────
    p_comments = sub.add_parser("comments", help="Lista los comentarios de un ticket")
    p_comments.add_argument("id", type=int, metavar="ID", help="ID del work item")
    _add_creds(p_comments)

    # ── states ────────────────────────────────────────────────────────────────
    p_states = sub.add_parser("states", help="Lista los estados disponibles")
    _add_creds(p_states)

    # ── types ─────────────────────────────────────────────────────────────────
    p_types = sub.add_parser("types", help="Lista los tipos de work item disponibles")
    _add_creds(p_types)

    return parser


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    action = args.action

    # Resolver credenciales
    try:
        org, project, pat_enc = _resolve(args)
        client = AdoClient(org, project, pat_enc)
    except AdoError as e:
        _err(action, str(e), "config")
    except Exception as e:
        _err(action, str(e), "config")

    # Despachar acción
    try:
        if action == "list":
            result = client.list_work_items(
                state=args.state,
                search=args.search,
                limit=args.limit,
                include_closed=args.all,
            )
            _ok(action, result, count=len(result))

        elif action == "get":
            _ok(action, client.get_work_item(args.id))

        elif action == "create":
            result = client.create_work_item(
                title=args.title,
                description=args.desc,
                wi_type=args.type,
                priority=args.priority,
                area_path=args.area,
                assigned_to=args.assigned,
                tags=args.tags,
                is_html=args.html,
            )
            _ok(action, result)

        elif action == "comment":
            result = client.add_comment(args.id, args.text, is_html=args.html)
            _ok(action, result)

        elif action == "state":
            result = client.update_state(args.id, args.state)
            _ok(action, result)

        elif action == "comments":
            result = client.list_comments(args.id)
            _ok(action, result, count=len(result))

        elif action == "states":
            _ok(action, client.get_states())

        elif action == "types":
            _ok(action, client.get_types())

    except AdoError as e:
        _err(action, str(e), f"ado_api_{e.status}" if e.status else "ado_api")
    except Exception as e:
        _err(action, str(e), "unexpected")


if __name__ == "__main__":
    main()
