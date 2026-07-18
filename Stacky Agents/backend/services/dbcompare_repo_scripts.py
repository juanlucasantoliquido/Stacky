"""Plan 180 — Puente diff→repo: índice read-only de scripts SQL ticketeados.

HITL absoluto: este módulo SOLO informa. Nunca excluye ítems del diff, nunca
edita ni ejecuta scripts, nunca escribe bajo el workspace (única escritura:
data_dir()/db_compare/repo_scripts/index.json).

Convención del prior art (evidencia services/glossary.py:25):
    trunk/BD/1 - Inicializacion BD/600804 - Inserts RIDIOMA.sql
=> ticket = primer grupo de 4-7 dígitos al inicio del nombre (fallback: carpetas).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path, PurePosixPath

import runtime_paths

logger = logging.getLogger(__name__)

INDEX_VERSION = 1
_INDEX_DIRNAME = "db_compare/repo_scripts"

_TICKET_RE = re.compile(r"^\s*(\d{4,7})\b")

# Comentarios SQL (fix C6 v2): se PODAN antes de extraer tablas. Limite declarado:
# un '--' o '/*' DENTRO de un literal de string tambien se poda (no hay parser);
# falso negativo teorico infimo, aceptado.
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"--[^\r\n]*")

# Regex de sentencias DML/DDL soportadas (case-insensitive, sobre el TEXTO COMPLETO
# ya sin comentarios — fix C11 v2). LIMITES DECLARADOS: ver docstring de extract_tables.
_TABLE_PATTERNS = (
    re.compile(r"\b(?:CREATE|ALTER)\s+TABLE\s+([\[\]\"\w.]+)", re.IGNORECASE),
    re.compile(r"\b(?:CREATE(?:\s+OR\s+ALTER)?|ALTER)\s+VIEW\s+([\[\]\"\w.]+)", re.IGNORECASE),  # fix C5 v2
    re.compile(r"\bINSERT\s+INTO\s+([\[\]\"\w.]+)", re.IGNORECASE),
    re.compile(r"\bUPDATE\s+([\[\]\"\w.]+)\s+SET\b", re.IGNORECASE),
    re.compile(r"\bDELETE\s+FROM\s+([\[\]\"\w.]+)", re.IGNORECASE),
    re.compile(r"\bMERGE\s+INTO\s+([\[\]\"\w.]+)", re.IGNORECASE),
)


def infer_ticket(rel_path: str) -> str | None:
    """Regla literal: 1) nombre de archivo; 2) segmentos de carpeta del más
    profundo al más superficial. Primer match de _TICKET_RE gana. None si nada."""
    parts = PurePosixPath(rel_path).parts
    if not parts:
        return None
    for segment in (parts[-1], *reversed(parts[:-1])):
        m = _TICKET_RE.match(segment)
        if m:
            return m.group(1)
    return None


def _strip_sql_comments(sql_text: str) -> str:
    return _LINE_COMMENT_RE.sub(" ", _BLOCK_COMMENT_RE.sub(" ", sql_text or ""))


def _clean_identifier(raw: str) -> tuple[str | None, str | None]:
    """'[dbo].[RIDIOMA]' -> ('RIDIOMA', 'DBO.RIDIOMA'); 'RIDIOMA' -> ('RIDIOMA', None).
    Identificadores que empiezan con '#' o '@' (temporales/variables) -> (None, None)."""
    cleaned = raw.replace("[", "").replace("]", "").replace('"', "").strip().rstrip(";,")
    if not cleaned or cleaned[0] in ("#", "@"):
        return None, None
    segments = [s for s in cleaned.split(".") if s]
    if not segments:
        return None, None
    table = segments[-1].upper()
    qualified = f"{segments[-2].upper()}.{table}" if len(segments) >= 2 else None
    return table, qualified


def extract_tables(sql_text: str) -> tuple[list[str], list[str]]:
    """Devuelve (tables, tables_qualified) dedup + orden alfabético.

    LÍMITES DECLARADOS (aceptados; el resultado es SOLO informativo):
    - Los comentarios `--` y `/* */` se PODAN antes de matchear (fix C6): una
      sentencia comentada NO cuenta. Contrapartida ínfima: un '--' dentro de un
      literal de string también se poda.
    - No ve SQL dinámico (EXEC / sp_executesql con strings concatenados).
    - Idiom MSSQL `UPDATE alias SET ... FROM tabla alias`: captura el ALIAS como
      tabla (falso positivo declarado, fix C7 — no hay parser).
    - No resuelve sinónimos ni vistas intermedias.
    - Descarta tablas temporales (#t) y variables de tabla (@t).
    """
    text = _strip_sql_comments(sql_text)
    tables: set[str] = set()
    qualified: set[str] = set()
    for pattern in _TABLE_PATTERNS:
        for match in pattern.finditer(text):
            table, qual = _clean_identifier(match.group(1))
            if table:
                tables.add(table)
            if qual:
                qualified.add(qual)
    return sorted(tables), sorted(qualified)


# ─────────────────── F2 — Escáner read-only ACOTADO + índice ───────────────────

_EXCLUDED_DIR_NAMES = {
    "node_modules", ".git", ".svn", "venv", ".venv", "bin", "obj",
    "packages", "dist", "build", "__pycache__", ".vs",
}
_SCAN_BUDGET_SEC = 10  # presupuesto DURO de tiempo por escaneo (fix C1): al
                       # excederlo, el walk corta y el índice sale truncated="budget".
                       # Constante interna deliberada (no flag): el refresh manual
                       # permite reintentar; subirla es decisión de código, no de config.


def _index_path() -> Path:
    d = runtime_paths.data_dir() / _INDEX_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d / "index.json"


def _valid_globs(raw: list[str]) -> list[str]:
    """Fix C2: descarta patrones que podrían escapar del workspace o crashear el
    walk — absolutos, con ':' (drive letter), o con componente '..'. Nunca lanza."""
    out = []
    for g in raw:
        norm = g.replace("\\", "/").strip()
        if not norm:
            continue
        if norm.startswith("/") or ":" in norm or any(part == ".." for part in norm.split("/")):
            logger.info("repo bridge: glob descartado por inseguro: %r", g)
            continue
        out.append(norm)
    return out


def _globs() -> list[str]:
    import config as _config
    raw = str(getattr(_config.config, "STACKY_DB_COMPARE_REPO_BRIDGE_GLOBS",
                      "trunk/BD/**/*.sql,**/BD/**/*.sql"))
    return _valid_globs([g for g in raw.split(",") if g.strip()])


def _max_files() -> int:
    import config as _config
    try:
        val = int(getattr(_config.config, "STACKY_DB_COMPARE_REPO_BRIDGE_MAX_FILES", 5000))
    except (TypeError, ValueError):
        val = 5000
    return max(100, min(val, 50000))


def _iter_sql_files(root: Path, globs: list[str], cap: int, deadline: float):
    """Walk ACOTADO (fix C1 v2 — reemplaza al glob de pathlib, que materializaba
    el árbol entero antes de cap/exclusiones):
    - os.walk(topdown=True) con PRUNE in-place de dirnames: excluidos por nombre
      + symlinks + junctions NT (fix C3) se podan ANTES de descender.
    - Matching por ruta relativa posix lowercase contra los globs con
      PurePosixPath.full_match (py3.13 — venv canónico del repo).
    - Corta el WALK (no solo el resultado) al alcanzar `cap` o `deadline`.
    Retorna (paths, truncated_reason | None, dirs_pruned)."""
    patterns = [p.lower() for p in globs]
    out: list[Path] = []
    dirs_pruned = 0
    if not patterns:
        return out, None, dirs_pruned
    for dirpath, dirnames, filenames in os.walk(str(root), topdown=True):
        if time.monotonic() > deadline:
            return out, "budget", dirs_pruned
        kept = []
        for d in sorted(dirnames):
            full = os.path.join(dirpath, d)
            if d in _EXCLUDED_DIR_NAMES or os.path.islink(full) or os.path.isjunction(full):
                dirs_pruned += 1
                continue
            kept.append(d)
        dirnames[:] = kept  # prune REAL: os.walk no desciende a los podados
        for fname in sorted(filenames):
            if not fname.lower().endswith(".sql"):
                continue
            full_path = Path(dirpath) / fname
            rel = full_path.relative_to(root).as_posix()
            if not any(PurePosixPath(rel.lower()).full_match(p) for p in patterns):
                continue
            if len(out) >= cap:
                return out, "max_files", dirs_pruned
            out.append(full_path)
    return out, None, dirs_pruned


def build_index() -> dict | None:
    """Escanea el workspace ACTIVO (runtime_paths._active_workspace_root(),
    runtime_paths.py:66) y persiste el índice atómico. None si no hay workspace.
    READ-ONLY sobre el workspace: la única escritura es el index.json en data_dir()."""
    root = runtime_paths._active_workspace_root()
    if root is None:
        return None
    started = time.monotonic()
    files, truncated_reason, dirs_pruned = _iter_sql_files(
        root, _globs(), _max_files(), started + _SCAN_BUDGET_SEC
    )
    scripts = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")  # fix C8: BOM tolerado
            stat = path.stat()
        except OSError:
            continue  # archivo desaparecido/inaccesible: se saltea, no rompe
        tables, tables_qualified = extract_tables(text)
        scripts.append({
            "path": rel,
            "ticket": infer_ticket(rel),
            "tables": tables,
            "tables_qualified": tables_qualified,
            "mtime": int(stat.st_mtime),
            "size_bytes": int(stat.st_size),
            "sha256_12": hashlib.sha256(text.encode("utf-8")).hexdigest()[:12],
        })
    scripts.sort(key=lambda s: s["path"])
    from datetime import datetime, timezone
    index = {
        "version": INDEX_VERSION,
        "workspace_root": str(root),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "globs": _globs(),
        "files_scanned": len(scripts),
        "truncated": truncated_reason is not None,
        "truncated_reason": truncated_reason,
        "scan_duration_ms": int((time.monotonic() - started) * 1000),
        "dirs_pruned": dirs_pruned,
        "scripts": scripts,
    }
    path = _index_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(path))
    return index


def load_index() -> dict | None:
    path = _index_path()
    if not path.exists():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if doc.get("version") != INDEX_VERSION:
        return None
    return doc


def load_index_for(root: Path) -> dict | None:
    """Fix C4 (KPI-8): un índice persistido de OTRO workspace se trata como
    inexistente — la cobertura jamás cruza proyectos."""
    doc = load_index()
    if doc is None:
        return None
    if str(doc.get("workspace_root") or "") != str(root):
        return None
    return doc


# ─────────────────── F3 — Cobertura del diff (pura) ───────────────────

def match_diff_items(diff: dict, index: dict) -> dict:
    """Cruza items del SchemaDiff v1 (services/dbcompare_diff.py:311-331) con el
    RepoScriptIndex v1. PURA: no lee disco ni red. SOLO informa (HITL).

    Regla de matching (literal):
    - object_type "table" y "view": candidato = script cuyo `tables` contiene
      NAME.upper() O cuyo `tables_qualified` contiene f"{SCHEMA}.{NAME}".upper().
    - object_type "sequence": candidatos SIEMPRE [] (regla explícita: la
      extracción de F1 no captura sentencias de secuencias).
    - matched_by por candidato ([ADICIÓN ARQUITECTO] v2): "SCHEMA.TABLE" si el
      match fue calificado (señal fuerte), "TABLE" si fue por nombre pelado
      (posible homónimo cross-schema — el operador juzga).
    - Ranking: calificados primero; después mtime descendente; empate -> path.
    """
    scripts = index.get("scripts") or []
    out_items = []
    covered = 0
    for item in diff.get("items") or []:
        name_u = str(item.get("name") or "").upper()
        qual_u = f"{str(item.get('schema') or '').upper()}.{name_u}"
        candidates = []
        if item.get("object_type") != "sequence":
            for s in scripts:
                qualified_hit = qual_u in (s.get("tables_qualified") or [])
                if qualified_hit or name_u in (s.get("tables") or []):
                    candidates.append((s, "SCHEMA.TABLE" if qualified_hit else "TABLE"))
            candidates.sort(key=lambda pair: (
                0 if pair[1] == "SCHEMA.TABLE" else 1,
                -int(pair[0].get("mtime") or 0),
                pair[0].get("path") or "",
            ))
        if candidates:
            covered += 1
        out_items.append({
            "object_type": item.get("object_type"),
            "schema": item.get("schema"),
            "name": item.get("name"),
            "action": item.get("action"),
            "severity": item.get("severity"),
            "candidates": [
                {"path": s["path"], "ticket": s.get("ticket"), "mtime": s.get("mtime"),
                 "matched_by": matched_by}
                for s, matched_by in candidates[:10]  # cap de candidatos por ítem, declarado
            ],
        })
    return {
        "items": out_items,
        "covered_count": covered,
        "total_count": len(out_items),
    }
