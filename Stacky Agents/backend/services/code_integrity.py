"""services/code_integrity.py — Plan 130: gate determinista de integridad de codigo.

Dos checks, sin IA, sin ejecutar codigo, sin escribir nada:
- CHECK-1 (sintaxis): ast.parse en memoria de todos los .py del backend.
- CHECK-2 (imports de primera parte): todo import/from-import cuyo modulo raiz
  sea de primera parte debe resolver a un archivo/paquete existente.

Contrato del reporte y reglas de resolucion: ver Stacky Agents/docs/130_PLAN_*.md SS4.
"""
from __future__ import annotations

import ast
from pathlib import Path
from time import perf_counter

_EXCLUDED_DIRS = {".venv", "venv", "env", ".env", "__pycache__", "node_modules", ".git", ".pytest_cache", "data", "outputs"}
_PY_SUFFIX = ".py"
_EXEMPT_EXCEPTIONS = {"ImportError", "ModuleNotFoundError", "Exception"}


def backend_root() -> Path:
    """Raiz por defecto: el paquete vive en backend/services/ -> raiz = backend/."""
    return Path(__file__).resolve().parents[1]


def iter_py_files(root: Path) -> list[Path]:
    """Recorrido recursivo saltando _EXCLUDED_DIRS por NOMBRE en cualquier nivel.
    Solo archivos *.py. Orden determinista (sorted)."""
    result: list[Path] = []
    stack: list[Path] = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name in _EXCLUDED_DIRS:
                    continue
                stack.append(entry)
            elif entry.is_file() and entry.suffix == _PY_SUFFIX:
                result.append(entry)
    return sorted(result)


def first_party_names(root: Path) -> set[str]:
    """Nombres de primera parte en el NIVEL RAIZ de root: stems de *.py y nombres
    de directorios no excluidos que contengan __init__.py."""
    names: set[str] = set()
    try:
        entries = list(root.iterdir())
    except OSError:
        return names
    for entry in entries:
        if entry.is_file() and entry.suffix == _PY_SUFFIX:
            names.add(entry.stem)
        elif entry.is_dir() and entry.name not in _EXCLUDED_DIRS:
            if (entry / "__init__.py").exists():
                names.add(entry.name)
    return names


def resolve_module(root: Path, dotted: str) -> bool:
    """"a.b.c" resuelve si existe root/a/b/c.py O root/a/b/c/__init__.py."""
    parts = dotted.split(".")
    target = root
    for part in parts[:-1]:
        target = target / part
    last = parts[-1]
    return (target / f"{last}.py").exists() or (target / last / "__init__.py").exists()


def _exception_names(expr: ast.expr | None) -> set[str]:
    if expr is None:
        return set()
    if isinstance(expr, ast.Name):
        return {expr.id}
    if isinstance(expr, ast.Tuple):
        names: set[str] = set()
        for elt in expr.elts:
            names |= _exception_names(elt)
        return names
    if isinstance(expr, ast.Attribute):
        return {expr.attr}
    return set()


def collect_exempt_linenos(tree: ast.AST) -> set[int]:
    """Linenos de imports dentro de un ast.Try cuyo algun handler captura
    ImportError/ModuleNotFoundError/Exception (exencion anti-falso-positivo)."""
    exempt: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        caught: set[str] = set()
        for handler in node.handlers:
            caught |= _exception_names(handler.type)
        if not (caught & _EXEMPT_EXCEPTIONS):
            continue
        for stmt in node.body:
            for sub in ast.walk(stmt):
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    exempt.add(sub.lineno)
    return exempt


def _resolve_relative(path: Path, level: int, module: str | None) -> bool:
    base = path.parent
    for _ in range(level - 1):
        base = base.parent
    if module is None:
        return base.exists()
    parts = module.split(".")
    target = base
    for part in parts[:-1]:
        target = target / part
    last = parts[-1]
    return (target / f"{last}.py").exists() or (target / last / "__init__.py").exists()


def check_file(root: Path, path: Path, first_party: set[str]) -> tuple[dict | None, list[dict]]:
    """Parsea UNA vez. SyntaxError/ValueError -> (finding, []). Si parsea ok,
    valida CHECK-2 sobre el AST -> (None, broken_imports)."""
    rel = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        return {"file": rel, "line": exc.lineno or 0, "message": exc.msg}, []
    except ValueError as exc:
        return {"file": rel, "line": 0, "message": str(exc)}, []

    exempt = collect_exempt_linenos(tree)
    broken: list[dict] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if node.lineno in exempt:
                continue
            for alias in node.names:
                dotted = alias.name
                root_name = dotted.split(".")[0]
                if root_name in first_party and not resolve_module(root, dotted):
                    broken.append({
                        "file": rel, "line": node.lineno, "import": dotted,
                        "message": "modulo de primera parte no encontrado",
                    })
        elif isinstance(node, ast.ImportFrom):
            if node.lineno in exempt:
                continue
            if node.level and node.level >= 1:
                if not _resolve_relative(path, node.level, node.module):
                    dotted_display = ("." * node.level) + (node.module or "")
                    broken.append({
                        "file": rel, "line": node.lineno, "import": dotted_display,
                        "message": "modulo de primera parte no encontrado",
                    })
            elif node.module:
                root_name = node.module.split(".")[0]
                if root_name in first_party and not resolve_module(root, node.module):
                    broken.append({
                        "file": rel, "line": node.lineno, "import": node.module,
                        "message": "modulo de primera parte no encontrado",
                    })
    return None, broken


def run_checks(root: Path | None = None) -> dict:
    """Ensambla el reporte completo (contrato SS4.3)."""
    start = perf_counter()
    resolved_root = root if root is not None else backend_root()
    first_party = first_party_names(resolved_root)
    files = iter_py_files(resolved_root)

    syntax_errors: list[dict] = []
    broken_imports: list[dict] = []
    for path in files:
        finding, broken = check_file(resolved_root, path, first_party)
        if finding is not None:
            syntax_errors.append(finding)
        broken_imports.extend(broken)

    syntax_errors.sort(key=lambda d: (d["file"], d["line"]))
    broken_imports.sort(key=lambda d: (d["file"], d["line"]))
    elapsed_ms = int((perf_counter() - start) * 1000)

    return {
        "ok": not syntax_errors and not broken_imports,
        "root": str(resolved_root),
        "files_scanned": len(files),
        "elapsed_ms": elapsed_ms,
        "syntax_errors": syntax_errors,
        "broken_imports": broken_imports,
    }
