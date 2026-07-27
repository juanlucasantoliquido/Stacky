"""Plan 201 F1 — Scanner determinista de soluciones .sln.

Módulo PURO: recorre el workspace del cliente y devuelve el catálogo de `.sln`
con sus proyectos clasificados. Sin LLM, sin red, sin estado — el mismo árbol
siempre da el mismo catálogo, así que los 3 runtimes ven exactamente lo mismo.

Acotado por diseño (profundidad y cantidad de entradas): un repo gigante nunca
puede colgar el escaneo; si topa el tope, lo DECLARA con `truncated`.
"""
from __future__ import annotations

import os
import re

_IGNORE_DIRS = ("node_modules", ".git", "venv", ".venv", "bin", "obj",
                "__pycache__", "packages", ".vs", "TestResults", "dist", "node")
_MAX_DEPTH = 8          # los repos de cliente anidan más que un repo de app
_MAX_ENTRIES = 5000     # tope duro anti-cuelgue
_CSPROJ_HEAD_BYTES = 65536
_WEB_SDK = "microsoft.net.sdk.web"
_WORKER_SDK = "microsoft.net.sdk.worker"
_WEB_GUID = "349c5851-65df-11da-9384-00065b846f21"  # ProjectTypeGuid web clásico

_SLN_PROJECT_RE = re.compile(
    r'Project\("\{[0-9A-Fa-f-]+\}"\)\s*=\s*"([^"]+)",\s*"([^"]+)",\s*"\{[0-9A-Fa-f-]+\}"'
)


# ── Helpers privados ─────────────────────────────────────────────────────────

def _dedupe(slug: str, seen: set) -> str:
    """Unicidad estable por orden: 'x', 'x-2', 'x-3'... Muta `seen`."""
    cand = slug
    n = 2
    while cand in seen:
        cand = f"{slug}-{n}"
        n += 1
    seen.add(cand)
    return cand


def _title_case(name: str) -> str:
    """'MiSolucion' -> 'Mi Solucion'; 'mi_solucion.core' -> 'Mi Solucion Core'.

    Un `.title()` naive daría 'Misolucion' (mal): hay que separar el camelCase
    ANTES de capitalizar.
    """
    s = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', name or '')
    s = re.sub(r'[._\-]+', ' ', s)
    words = [w for w in s.split() if w]
    return ' '.join(w[:1].upper() + w[1:] for w in words) or (name or '')


def _read_text_safe(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _read_head_bytes(path: str, n: int) -> str:
    with open(path, "rb") as fh:
        return fh.read(n).decode("utf-8", errors="replace")


def _first_group(pattern: str, text: str) -> str:
    m = re.search(pattern, text)
    return m.group(1).strip() if m else ""


def _infer_project(csproj_path: str) -> tuple:
    """Tipo del proyecto por señales deterministas. Nunca lanza."""
    try:
        text = _read_head_bytes(csproj_path, _CSPROJ_HEAD_BYTES).lower()
    except OSError:
        return ("unknown", "")
    tfm = _first_group(r'<targetframework[^>]*>([^<]+)</targetframework', text)
    proj_dir = os.path.dirname(csproj_path)
    web = (_WEB_SDK in text) or (_WEB_GUID in text) \
        or os.path.exists(os.path.join(proj_dir, "web.config"))
    if web:
        return ("web", tfm)
    if _WORKER_SDK in text:
        return ("service", tfm)
    if "<outputtype>exe</outputtype>" in text or "<outputtype>winexe</outputtype>" in text:
        return ("console", tfm)
    return ("library", tfm)


def _parse_sln_projects(sln_path: str) -> list:
    """Proyectos declarados en el `.sln`, con rutas resueltas. Nunca lanza."""
    try:
        text = _read_text_safe(sln_path)
    except OSError:
        return []
    sln_dir = os.path.dirname(sln_path)
    projects: list = []
    for m in _SLN_PROJECT_RE.finditer(text):
        proj_name, rel = m.group(1), m.group(2).replace("\\", os.sep)
        low = rel.lower()
        if not (low.endswith(".csproj") or low.endswith(".vbproj")):
            continue
        csproj = os.path.normpath(os.path.join(sln_dir, rel))
        ptype, tfm = _infer_project(csproj)
        projects.append({"name": proj_name, "csproj_path": csproj,
                         "type": ptype, "target_framework": tfm})
    return projects


# ── API pública ──────────────────────────────────────────────────────────────

def slugify_solution(name: str) -> str:
    """Slug que el bridge de despliegues acepta como app id: [a-z0-9][a-z0-9_-]{0,63}."""
    s = re.sub(r'[^a-z0-9]+', '-', (name or '').strip().lower()).strip('-')
    if not s or not s[0].isalnum():
        s = 'sln-' + s
    s = s[:64].rstrip('-')
    return s or 'sln'


def scan_solutions_ex(workspace_root) -> dict:
    """`{"solutions": [...], "truncated": bool}`. Read-only, nunca lanza."""
    if not workspace_root or not os.path.isdir(workspace_root):
        return {"solutions": [], "truncated": False}
    root = os.path.normpath(workspace_root)
    sln_paths: list = []
    scanned = 0
    truncated = False
    for dirpath, dirnames, filenames in os.walk(root):
        depth = dirpath[len(root):].count(os.sep)
        if depth >= _MAX_DEPTH:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS]
        for fname in filenames:
            scanned += 1
            if scanned > _MAX_ENTRIES:
                truncated = True
                break
            if fname.lower().endswith(".sln"):
                sln_paths.append(os.path.join(dirpath, fname))
        if truncated:
            break

    out: list = []
    seen_slugs: set = set()
    for sln in sorted(sln_paths):
        name = os.path.splitext(os.path.basename(sln))[0]
        slug = _dedupe(slugify_solution(name), seen_slugs)
        out.append({
            "slug": slug,
            "sln_path": sln,
            "sln_name": name,
            "friendly_name": _title_case(name),
            "projects": _parse_sln_projects(sln),
        })
    return {"solutions": out, "truncated": truncated}


def scan_solutions(workspace_root) -> list:
    """Wrapper de compatibilidad: solo la lista de soluciones."""
    return scan_solutions_ex(workspace_root)["solutions"]


# ── Plan 215 F3 (ADITIVO) — alta manual de una .sln concreta ────────────────
def scan_single_solution(sln_path: str, existing_slugs=None):
    """Entrada de catálogo de UNA .sln concreta (alta manual del Plan 215).

    Devuelve un dict con el MISMO shape que produce `scan_solutions_ex`, o None
    si la ruta no es un `.sln` legible. No lanza nunca.
    """
    if not sln_path or not sln_path.lower().endswith(".sln"):
        return None
    try:
        if not os.path.isfile(sln_path):
            return None
    except (OSError, ValueError):
        return None
    name = os.path.splitext(os.path.basename(sln_path))[0]
    seen = set(existing_slugs or [])
    slug = _dedupe(slugify_solution(name), seen)
    return {
        "slug": slug,
        "sln_path": os.path.normpath(sln_path),
        "sln_name": name,
        "friendly_name": _title_case(name),
        "projects": _parse_sln_projects(sln_path),
    }
