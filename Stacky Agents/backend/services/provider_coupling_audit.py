"""services/provider_coupling_audit.py -- Plan 218 F1.

Censo determinista del acoplamiento a un proveedor concreto (hoy: Azure DevOps).
PURO: solo lee archivos, sin red, sin DB, sin importar el código auditado.

Convierte el acoplamiento en un NÚMERO MEDIDO que el ratchet
(tests/test_plan218_coupling_ratchet.py) solo deja bajar.

Semántica de alcance, calibrada contra los números del propio plan (§1 K2..K4,
medidos 2026-07-25):
  * `ado_importer_*` EXCLUYE la familia `services/ado_*.py` — un adaptador ADO
    que importa a otro adaptador ADO no es acoplamiento del núcleo (36 archivos).
  * `tracker_literal_*` la INCLUYE — la meta de K4 ("≤ 20: adaptadores + factories
    + defaults") cuenta explícitamente a los adaptadores (82 líneas).
  * Ambos excluyen `tests/`, `.venv/`, `venv/`, `__pycache__/`.
"""
from __future__ import annotations

import re
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]

_EXCLUDED_PARTS = ("tests", ".venv", "venv", "__pycache__", "node_modules")

# Módulos que TIENEN derecho a importar services.ado_* (adaptadores + seam ADO-only).
# Es la META de K2 (≤ 6 archivos), no una exclusión del censo.
ADAPTER_ALLOWLIST: frozenset[str] = frozenset({
    "services/tracker_provider.py", "services/ci_provider.py",
    "services/ci_logs_provider.py", "services/ci_preflight.py",
    "services/ci_variables.py", "services/project_context.py",
})

# v2 (C5): archivos NEUTRALES del sustrato 218 que nombran a los DOS proveedores por
# definición (son el registro, no un acoplamiento). Sin esto, implementar F2 después de
# F1 rompe el ratchet de literales: CAPABILITY_MATRIX tiene "azure_devops" como CLAVE.
NEUTRAL_REGISTRY_ALLOWLIST: frozenset[str] = frozenset({
    "services/provider_capabilities.py",   # F2 — la matriz
    "services/provider_coupling_audit.py",  # F1 — este mismo censo
    "services/flag_binding_audit.py",      # F0 — el audit de binding
    "services/tracker_vocabulary.py",      # F5 — vocabulario canónico
    "services/parity_rollout.py",          # F8 — evaluación de capacidades
    "api/parity.py",                       # F8 — endpoint de solo lectura
})

# Cubre las 3 formas de importar un módulo de la familia ADO: import calificado del
# submódulo (con y sin `from`), y el import del paquete `services` trayendo el nombre
# suelto. La prosa evita deletrear las formas literales a propósito: este archivo es
# auditado por su propio censo (memoria `gotcha-plan-comment-matches-own-gate`).
_ADO_IMPORT_RE = re.compile(
    r"(?:from|import)\s+services\.ado_\w+"
    r"|from\s+services\s+import\s+\(?[^\n]*\bado_\w+"
)
_TRACKER_LITERAL_RE = re.compile(r'"azure_devops"')
_ADO_CLIENT_CALL = "_ado_client_for_ticket("
_ADO_ROUTE_RE = re.compile(r"by-ado|publish-to-ado|/ado-")


def _python_files() -> list[Path]:
    return sorted(
        p for p in _BACKEND.rglob("*.py")
        if not any(part in _EXCLUDED_PARTS for part in p.relative_to(_BACKEND).parts)
    )


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def scan_backend_coupling() -> dict:
    """Censo del acoplamiento a ADO. Salida determinista (claves ordenadas).

    Nombres con UNIDAD explícita (v2, C8): `*_file_count` cuenta ARCHIVOS,
    `*_occurrences` cuenta ocurrencias/líneas.
    """
    importer_files: dict[str, int] = {}
    literal_files: dict[str, int] = {}

    for path in _python_files():
        rel = path.relative_to(_BACKEND).as_posix()
        text = _read(path)
        if not text:
            continue

        if not rel.startswith("services/ado_"):
            hits = len(_ADO_IMPORT_RE.findall(text))
            if hits:
                importer_files[rel] = hits

        if rel not in NEUTRAL_REGISTRY_ALLOWLIST:
            lineas = sum(1 for line in text.splitlines() if _TRACKER_LITERAL_RE.search(line))
            if lineas:
                literal_files[rel] = lineas

    tickets = _read(_BACKEND / "api" / "tickets.py")
    ado_client_lines = sum(1 for line in tickets.splitlines() if _ADO_CLIENT_CALL in line)

    ado_routes = 0
    for path in sorted((_BACKEND / "api").glob("*.py")):
        ado_routes += sum(
            1 for line in _read(path).splitlines() if _ADO_ROUTE_RE.search(line)
        )

    return {
        "ado_importer_files": dict(sorted(importer_files.items())),
        "ado_importer_file_count": len(importer_files),
        "ado_importer_occurrences": sum(importer_files.values()),
        "tracker_literal_files": dict(sorted(literal_files.items())),
        "tracker_literal_file_count": len(literal_files),
        "tracker_literal_occurrences": sum(literal_files.values()),
        "ado_client_lines_in_tickets": ado_client_lines,
        "ado_route_count": ado_routes,
    }


def render_report_markdown(scan: dict) -> str:
    """Tabla Markdown del censo. PURA."""
    lineas = [
        "# Censo de acoplamiento a Azure DevOps (Plan 218 F1)",
        "",
        "| Métrica | Valor |",
        "|---|---|",
        f"| `ado_importer_file_count` | {scan['ado_importer_file_count']} |",
        f"| `ado_importer_occurrences` | {scan['ado_importer_occurrences']} |",
        f"| `tracker_literal_file_count` | {scan['tracker_literal_file_count']} |",
        f"| `tracker_literal_occurrences` | {scan['tracker_literal_occurrences']} |",
        f"| `ado_client_lines_in_tickets` | {scan['ado_client_lines_in_tickets']} |",
        f"| `ado_route_count` | {scan['ado_route_count']} |",
        "",
        "## Importadores de `services.ado_*` fuera de la allowlist de adaptadores",
        "",
    ]
    fuera = {
        k: v for k, v in scan["ado_importer_files"].items() if k not in ADAPTER_ALLOWLIST
    }
    if fuera:
        lineas.append("| Archivo | Ocurrencias |")
        lineas.append("|---|---|")
        lineas.extend(f"| `{k}` | {v} |" for k, v in sorted(fuera.items()))
    else:
        lineas.append("_Ninguno — meta K2 alcanzada._")
    return "\n".join(lineas) + "\n"
