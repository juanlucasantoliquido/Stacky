"""Plan 211 F2 — Barrido de residuos de port entre clientes (Capa C).

Cuando se porta trabajo de un cliente a otro quedan residuos: el servidor viejo,
una ruta del otro repo, el nombre del producto ajeno. Compilan igual, y por eso
el build verde no los atrapa. Este módulo arma el catálogo de tokens de los OTROS
clientes del registro y busca esos tokens en los archivos que tocó el Developer.

Dos guardas contra el falso positivo, que acá es caro (baja el gate del developer):
  - Match por LÍMITE DE PALABRA, nunca substring: `crea` no matchea `CrearCliente`.
  - Solo un token de ALTA CONFIANZA puede bloquear; uno corto o común avisa.
Y una válvula humana: `port_residue.allowlist` del perfil suprime lo legítimo.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_MIN_TOKEN_LEN = 4
_STOPWORDS = {"online", "batch", "test", "tests", "src", "app", "main", "code", "data",
              "trunk", "azure", "devops", "http", "https", "true", "false", "null",
              "none", "core", "base", "prod", "dev", "qa", "release", "debug",
              "windows", "system", "server", "local"}
_SOURCE_EXTS = (".cs", ".vb", ".csproj", ".sln", ".config", ".sql", ".aspx",
                ".cshtml", ".razor", ".resx")
_MAX_FILE_BYTES = 524288
_MAX_FINDINGS = 200
_SEVERITY = {"server": "blocking", "path": "blocking", "workspace": "blocking",
             "product": "warning", "client_label": "warning"}
_HICONF_LEN = 6


@dataclass(frozen=True)
class ResidueFinding:
    token: str
    kind: str
    severity: str
    file: str
    line: int
    evidence: str
    source_project: str


# ── Catálogo de tokens ajenos ────────────────────────────────────────────────

def _add(catalog: dict, value, source: str, kind: str) -> None:
    tok = (value or "").strip().lower()
    if len(tok) >= _MIN_TOKEN_LEN and tok not in _STOPWORDS and re.search(r"[a-z0-9]", tok):
        catalog.setdefault(tok, {"source_project": source, "kind": kind})


def _add_path_tokens(catalog: dict, path, source: str, kind: str) -> None:
    for seg in re.split(r"[\\/]+", (path or "")):
        _add(catalog, seg, source, kind)


def build_foreign_token_catalog(ticket_project) -> dict:
    """Tokens de los OTROS clientes. Excluye el proyecto DEL TICKET (no el activo
    global, que puede apuntar a otro cliente). Nunca lanza."""
    try:
        from project_manager import get_active_project, get_all_projects

        excl_name = (ticket_project or get_active_project() or "").strip().lower()
        all_cfgs = get_all_projects() or []
    except Exception:  # noqa: BLE001
        logger.debug("no se pudo listar proyectos para el catálogo", exc_info=True)
        return {}

    excl_ws = ""
    for cfg in all_cfgs:
        nombre = str(cfg.get("name") or cfg.get("project_name") or "").strip().lower()
        if nombre and nombre == excl_name:
            excl_ws = os.path.normpath(str(cfg.get("workspace_root") or ""))
            break

    catalog: dict = {}
    for cfg in all_cfgs:
        name = str(cfg.get("name") or cfg.get("project_name") or "").strip()
        ws = os.path.normpath(str(cfg.get("workspace_root") or ""))
        if (name and name.lower() == excl_name) or (excl_ws and ws == excl_ws):
            continue
        prof = cfg.get("client_profile") or {}
        term = prof.get("terminology") or {}
        db = prof.get("database") or {}
        cl = prof.get("code_layout") or {}
        _add(catalog, db.get("server"), name, "server")
        _add(catalog, term.get("product_name"), name, "product")
        _add(catalog, term.get("client_label"), name, "client_label")
        _add(catalog, os.path.basename(ws) if ws else "", name, "workspace")
        for p in (cl.get("online_path"), cl.get("batch_path"), cl.get("lib_path")):
            _add_path_tokens(catalog, p, name, "path")
    return catalog


def allowlist_for_project(project_name) -> list:
    """Tokens que el operador declaró legítimos en ESTE cliente. Nunca lanza."""
    try:
        from services.client_profile import load_effective_client_profile

        prof = load_effective_client_profile(project_name or "") or {}
    except Exception:  # noqa: BLE001
        return []
    val = (prof.get("port_residue") or {}).get("allowlist") or []
    return [str(t).strip().lower() for t in val if str(t).strip()]


# ── Escaneo ──────────────────────────────────────────────────────────────────

def _read_text(path: str) -> str:
    try:
        with open(path, "rb") as fh:
            return fh.read(_MAX_FILE_BYTES).decode("utf-8", errors="replace")
    except OSError:
        return ""


def _word_search(low_text: str, tok: str) -> bool:
    """Límite de palabra con lookarounds de no-alfanumérico: sirve para tokens con
    `. - _ / :` (hosts y rutas), donde `\\b` se comporta mal."""
    return re.search(r"(?<![a-z0-9])" + re.escape(tok) + r"(?![a-z0-9])",
                     low_text) is not None


def _high_confidence(tok) -> bool:
    return len(tok or "") >= _HICONF_LEN or bool(re.search(r"[0-9._\-\\/:]", tok or ""))


def _effective_severity(kind: str, tok: str) -> str:
    base = _SEVERITY.get(kind, "warning")
    if base == "blocking" and not _high_confidence(tok):
        # Un token corto o común NUNCA baja el gate del developer: solo avisa.
        return "warning"
    return base


def _trunc(s, n: int = 200) -> str:
    return (s or "").strip()[:n]


def _mask(s: str) -> str:
    try:
        from services.secret_masking import mask_token_values

        return mask_token_values(s)
    except Exception:  # noqa: BLE001
        logger.debug("secret_masking no disponible", exc_info=True)
        return s


def _first_line_with(text: str, tok: str) -> tuple:
    low_tok = tok.lower()
    for i, linea in enumerate((text or "").splitlines(), start=1):
        if low_tok in linea.lower():
            return i, linea
    return 0, ""


def scan_files_for_foreign_tokens(files: list, catalog: dict, *, workspace_root: str,
                                  allowlist: list | None = None) -> list:
    """Hallazgos de residuo. Nunca lanza; acotado por `_MAX_FINDINGS`."""
    if not catalog:
        return []
    allow = {str(t).strip().lower() for t in (allowlist or []) if str(t).strip()}
    out: list = []
    for rel in files or []:
        if not str(rel).lower().endswith(_SOURCE_EXTS):
            continue
        path = rel if os.path.isabs(str(rel)) else os.path.join(workspace_root or "", str(rel))
        text = _read_text(path)
        if not text:
            continue
        low = text.lower()
        for tok, meta in catalog.items():
            if tok in allow:
                continue
            if not _word_search(low, tok):
                continue
            linea, evidencia = _first_line_with(text, tok)
            out.append(ResidueFinding(
                token=tok, kind=meta["kind"],
                severity=_effective_severity(meta["kind"], tok),
                file=path, line=linea, evidence=_mask(_trunc(evidencia)),
                source_project=meta["source_project"],
            ))
            if len(out) >= _MAX_FINDINGS:
                return out
    return out


# ── Archivos tocados ─────────────────────────────────────────────────────────

def _git(ws: str, args: list) -> str:
    try:
        p = subprocess.run(["git", "-C", ws, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
        return p.stdout if p.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def _parse_porcelain(porcelain: str) -> list:
    """`XY <path>` o `XY <old> -> <new>`; los paths con espacios vienen entrecomillados."""
    out: list = []
    for raw in (porcelain or "").splitlines():
        if len(raw) < 4:
            continue
        entry = raw[3:]
        if " -> " in entry:
            entry = entry.split(" -> ", 1)[1]
        entry = entry.strip()
        if len(entry) >= 2 and entry[0] == '"' and entry[-1] == '"':
            try:
                entry = (entry[1:-1].encode("utf-8").decode("unicode_escape")
                         .encode("latin-1").decode("utf-8", "replace"))
            except Exception:  # noqa: BLE001
                entry = entry[1:-1]
        if entry:
            out.append(entry)
    return out


def changed_files(workspace_root, *, base_ref: str | None = None) -> list:
    """Archivos fuente que cambiaron. Git-only; sin repo devuelve [] (nunca lanza).

    Autoría: con `base_ref` el diff es confiable. Sin él, el working tree puede
    traer cambios de otra sesión — por eso la severidad exige alta confianza para
    bloquear: un archivo ajeno jamás voltea el gate por un token dudoso.
    """
    if not workspace_root or not os.path.isdir(str(workspace_root)):
        return []
    ws = str(workspace_root)
    if base_ref:
        diff = _git(ws, ["diff", "--name-only", f"{base_ref}..HEAD"])
        files = [l.strip() for l in diff.splitlines() if l.strip()]
        if files:
            return [f for f in files if f.lower().endswith(_SOURCE_EXTS)]
    files = _parse_porcelain(_git(ws, ["status", "--porcelain", "--untracked-files=all"]))
    if not files:
        last = _git(ws, ["show", "--name-only", "--pretty=format:", "HEAD"])
        files = [l.strip() for l in last.splitlines() if l.strip()]
    return [f for f in files if f.lower().endswith(_SOURCE_EXTS)]


def residue_to_dicts(findings: list) -> list:
    """Shape que consume la seam de evidencia del gate de build."""
    return [{
        "kind": f.kind, "severity": f.severity, "file": f.file,
        "detail": f"token '{f.token}' de {f.source_project} ({f.kind})",
    } for f in findings or []]
