"""services/flag_binding_audit.py -- Plan 218 F0 [ADICIÓN ARQUITECTO 1].

Auditoría de BINDING del nombre `config`. PURA: solo lee y parsea archivos con
`ast`, nunca los ejecuta ni hace I/O de red.

Generaliza de forma permanente la memoria `gotcha-config-config-vs-modulo-tickets`:
un módulo que hace `import config` (el MÓDULO) y lee una flag del nombre pelado
obtiene siempre el default de la clase — es decir, una RAMA MUERTA silenciosa.
Un módulo que hace `from config import config` bindea la INSTANCIA y sus lecturas
son CORRECTAS.

Por qué AST y no regex: hay ~69 coincidencias textuales de `getattr(config,` en
`services/` + `api/` y ~65 son CORRECTAS. Un centinela textual que exigiera
`config.config` en masa rompería el motor de flags (`Config` no tiene `.config`).
Lo que define el defecto NO es el texto: es el binding.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable, Optional

_BACKEND = Path(__file__).resolve().parents[1]
_SCAN_DIRS: tuple[str, ...] = ("services", "api", "harness")

# Prefijos de atributos que son FLAGS/CONFIG de la instancia (no submódulos ni helpers).
_FLAG_PREFIXES: tuple[str, ...] = (
    "STACKY_",
    "GITLAB_",
    "ADO_",
    "CLAUDE_CODE_CLI_",
    "CODEX_CLI_",
    "COPILOT_",
    "LLM_",
)

_MODULE_BINDING = "module"
_INSTANCE_BINDING = "instance"


def _is_flag_attr(attr: str) -> bool:
    # Regla 3: leer `config` (o sea `config.config...`) NUNCA es violación.
    if attr == "config":
        return False
    return any(attr.startswith(prefix) for prefix in _FLAG_PREFIXES)


def _collect_bindings(tree: ast.AST) -> dict[str, str]:
    """Devuelve {nombre local -> 'module' | 'instance'} para el nombre `config`."""
    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "config" or alias.name.startswith("config."):
                    local = alias.asname or alias.name.split(".")[0]
                    bindings[local] = _MODULE_BINDING
        elif isinstance(node, ast.ImportFrom):
            if node.module != "config" or node.level:
                continue
            for alias in node.names:
                if alias.name == "config":
                    bindings[alias.asname or alias.name] = _INSTANCE_BINDING
    return bindings


def _violations_in_source(rel_path: str, source: str) -> list[dict]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    bindings = _collect_bindings(tree)
    module_bound = {name for name, kind in bindings.items() if kind == _MODULE_BINDING}
    if not module_bound:
        return []

    found: list[dict] = []
    for node in ast.walk(tree):
        # (a) getattr(<name>, "FLAG", ...) — el primer argumento debe ser un Name pelado.
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and node.args
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id in module_bound
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
            and _is_flag_attr(node.args[1].value)
        ):
            found.append({
                "file": rel_path,
                "line": node.lineno,
                "name": node.args[0].id,
                "attr": node.args[1].value,
                "binding": _MODULE_BINDING,
            })
            continue

        # (b) acceso directo <name>.FLAG. `config.config.FLAG` NO entra acá porque
        #     el `value` del Attribute externo es otro Attribute, no un Name.
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in module_bound
            and _is_flag_attr(node.attr)
        ):
            found.append({
                "file": rel_path,
                "line": node.lineno,
                "name": node.value.id,
                "attr": node.attr,
                "binding": _MODULE_BINDING,
            })

    return found


def scan(
    root: Optional[Path | str] = None,
    scan_dirs: Optional[Iterable[str]] = None,
) -> dict:
    """Devuelve {"violations": [...], "violation_count": int, "module_bound_files": [...]}.

    Un sitio es VIOLACIÓN si y solo si:
      1) el nombre base está bindeado en ese módulo por `import config` /
         `import config as X` (apunta al MÓDULO), y
      2) se lee de él un atributo con uno de _FLAG_PREFIXES, sea por
         `getattr(<name>, "FLAG", ...)` o por acceso directo `<name>.FLAG`,
      3) y el atributo leído NO es `config` (leer `config.config.FLAG` es CORRECTO).

    Salida ordenada por (file, line) — determinista.
    """
    base = Path(root) if root is not None else _BACKEND
    dirs = tuple(scan_dirs) if scan_dirs is not None else _SCAN_DIRS

    violations: list[dict] = []
    module_bound_files: list[str] = []

    for dirname in dirs:
        directory = base / dirname
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.py")):
            rel = path.relative_to(base).as_posix()
            try:
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            bindings = _collect_bindings(tree)
            if any(kind == _MODULE_BINDING for kind in bindings.values()):
                module_bound_files.append(rel)
            violations.extend(_violations_in_source(rel, source))

    violations.sort(key=lambda v: (v["file"], v["line"], v["attr"]))
    return {
        "violations": violations,
        "violation_count": len(violations),
        "module_bound_files": sorted(module_bound_files),
    }


def render_report(scan_result: dict) -> str:
    """Reporte legible con archivo:línea y el binding detectado. PURA."""
    violations = scan_result.get("violations") or []
    if not violations:
        return "flag_binding_audit: 0 violaciones (ninguna flag leída del MÓDULO config)."

    lines = [
        f"flag_binding_audit: {len(violations)} violación(es) "
        "— flags leídas del MÓDULO `config` (rama muerta garantizada):",
    ]
    for v in violations:
        lines.append(
            f"  {v['file']}:{v['line']}  {v['name']}.{v['attr']}  (binding={v['binding']})"
        )
    lines.append(
        "  Fix: leer de la INSTANCIA (`config.config.<FLAG>` o "
        "`from config import config` + `config.<FLAG>`)."
    )
    return "\n".join(lines)
