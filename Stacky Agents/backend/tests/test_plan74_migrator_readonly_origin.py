"""Plan 74 F11 — Centinela AST: migrador NO invoca mutadores sobre el origen.

3 casos:
  1. Ningún mutador invocado sobre 'origin' en los módulos migrator_*.py.
  2. Ningún 'from services.ado_client import AdoClient' en migrator_*.py.
  3. Canario: snippet que llama origin.create_item es detectado por el centinela.
"""
import ast
import pathlib
import re

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_MIGRATOR_MODULES = list((_BACKEND / "services").glob("migrator_*.py"))

_MUTATORS = frozenset({
    "create_item", "update_item_state", "update_item_assignee",
    "post_comment", "upload_attachment", "link_attachment",
    "create_work_item", "update_work_item",
})

# Nombres de variable que denotan el ORIGEN (read-only)
_ORIGIN_NAMES = frozenset({"origin", "origin_provider", "src", "source"})


def _find_mutator_calls_on_origin(source_code: str) -> list[str]:
    """Devuelve lista de 'origin.mutador(...)' encontrados en el AST."""
    violations = []
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        method_name = func.attr
        if method_name not in _MUTATORS:
            continue
        # Revisar si el objeto base es una variable de "origen"
        obj = func.value
        if isinstance(obj, ast.Name) and obj.id in _ORIGIN_NAMES:
            violations.append(
                f"línea {node.lineno}: {obj.id}.{method_name}(...) — mutador sobre origen"
            )
    return violations


# ── Caso 1: ningún mutador invocado sobre origin en migrator_*.py ─────────────

def test_no_mutators_on_origin_in_migrator_modules():
    """Ningún mutador se invoca sobre parámetros 'origin' en los módulos migrator."""
    assert _MIGRATOR_MODULES, "No se encontraron módulos migrator_*.py en services/"
    all_violations = []
    for path in _MIGRATOR_MODULES:
        source = path.read_text(encoding="utf-8")
        violations = _find_mutator_calls_on_origin(source)
        for v in violations:
            all_violations.append(f"{path.name}: {v}")

    assert not all_violations, (
        "CENTINELA: mutadores invocados sobre el origen (read-only roto):\n"
        + "\n".join(all_violations)
    )


# ── Caso 2: ningún 'from services.ado_client import AdoClient' en migrator_*.py ─

def test_no_adoclient_import_in_migrator():
    """Los módulos migrator_*.py no importan AdoClient directamente."""
    assert _MIGRATOR_MODULES, "No se encontraron módulos migrator_*.py en services/"
    _ADO_CLIENT_IMPORT = re.compile(
        r"from\s+services\.ado_client\s+import\s+.*AdoClient"
    )
    violations = []
    for path in _MIGRATOR_MODULES:
        source = path.read_text(encoding="utf-8")
        for i, line in enumerate(source.splitlines(), 1):
            if _ADO_CLIENT_IMPORT.search(line):
                violations.append(f"{path.name}:{i}: {line.strip()}")

    assert not violations, (
        "CENTINELA: migrator_*.py importa AdoClient directamente (debe usar el puerto):\n"
        + "\n".join(violations)
    )


# ── Caso 3 (canario): snippet con origin.create_item ES detectado ────────────

def test_canary_snippet_detectado():
    """El centinela AST captura un snippet intencionalmente malo."""
    bad_snippet = """
def migrate(origin, dest):
    origin.create_item(None)  # violación: mutador sobre el origen
"""
    violations = _find_mutator_calls_on_origin(bad_snippet)
    assert violations, (
        "CANARIO fallido: el centinela NO detectó origin.create_item (gate de significancia)"
    )
