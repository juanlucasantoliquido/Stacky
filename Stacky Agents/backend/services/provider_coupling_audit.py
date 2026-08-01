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


# ══════════════════════════════════════════════════════════════════════════════
# Plan 281 F0 — Censo de sitios ADO-only (por AST, no por texto)
# ══════════════════════════════════════════════════════════════════════════════

# Constructores de cliente ADO. Un módulo que llama a cualquiera de estos está
# pidiendo explícitamente Azure DevOps.
ADO_BUILDERS: frozenset[str] = frozenset({
    "_ado_client_for_ticket", "build_ado_client", "_client_for_ticket_project",
})

# Seam provider-agnóstico. Si la función lo usa, YA rutea bien.
PROVIDER_SEAMS: frozenset[str] = frozenset({
    "_provider_for_ticket", "get_tracker_provider",
})

# Señales de que la función discrimina por tipo de tracker antes de construir el
# cliente. Heurística DELIBERADAMENTE laxa (sobre-perdona) para que lo que quede
# marcado sea indiscutible.
# OJO (Plan 281 v2/C1): esta laxitud es la razón por la que `app.py::_startup_sync`
# cae en `gateados` y NO en `ado_only`, aunque funcionalmente sea un agujero para
# GitLab. Para ese defecto la señal correcta es `ciegos_a_gitlab` (abajo), no
# endurecer esta heurística.
TRACKER_GUARDS: frozenset[str] = frozenset({
    "tracker_is_azure_devops", "_tracker_type_for", "resolve_project_context",
    "require_project_context",
})
TRACKER_LITERALS: frozenset[str] = frozenset({
    "azure_devops", "gitlab", "jira", "mantis",
})

# El resolvedor canónico: quien lo llama contempla TODOS los trackers, no sólo
# los que nombra por literal.
_RESOLVEDOR_CANONICO = "tracker_is_azure_devops"
_LITERAL_GITLAB = "gitlab"

# Sitios que tienen DERECHO a ser ADO-only, con el motivo escrito.
# Toda entrada nueva acá exige justificación en el PR: es la puerta trasera del gate.
ADO_ONLY_JUSTIFICADOS: dict[str, str] = {
    "api/tickets.py::_ado_client_for_ticket": "ES el constructor del cliente ADO del módulo",
    "services/local_diagnostics.py::_probe_ado": "sonda de diagnóstico DE Azure DevOps, por definición",
}

# Sitios gateados que quedan FUERA del alcance del Plan 281, con el motivo.
CIEGOS_A_GITLAB_TOLERADOS: dict[str, str] = {
    "api/projects.py::get_tracker_states": "estados del tablero por tracker — su equivalente GitLab es del Plan 282",
}

# `services/ado_*.py` queda afuera: un adaptador ADO tiene derecho a ser ADO-only.
# `services/project_context.py` queda afuera: ahí se DEFINE `build_ado_client`.
_ADO_ONLY_EXCLUDED_PREFIXES: tuple[str, ...] = ("services/ado_",)
_ADO_ONLY_EXCLUDED_FILES: frozenset[str] = frozenset({"services/project_context.py"})

# Un `.tracker_type` que cuelga de una de estas llamadas NO es la columna: es la
# verdad ya resuelta desde el config del proyecto.
_ORIGENES_RESUELTOS: frozenset[str] = frozenset({
    "resolve_project_context", "require_project_context",
    "get_tracker_provider", "_provider_for_ticket",
})
# Archivos donde `<algo>.tracker_type` ES la verdad resuelta, no la columna.
_ROUTING_EXCLUDED_FILES: frozenset[str] = frozenset({
    "services/project_context.py",
    "services/tracker_write_router.py",
})


def _nombre_llamado(node) -> str | None:
    """Nombre de la función invocada: acepta `f(...)` y `mod.f(...)`.

    Sin la rama `ast.Attribute` el censo daría CERO en
    `services/completion_sync.py`, que llama `project_context.build_ado_client(...)`
    por alias de módulo.
    """
    import ast as _ast

    fn = getattr(node, "func", None)
    if isinstance(fn, _ast.Name):
        return fn.id
    if isinstance(fn, _ast.Attribute):
        return fn.attr
    return None


def _archivos_censables(raiz: Path) -> list[Path]:
    """`<raiz>/*.py` + `<raiz>/api/*.py` + `<raiz>/services/*.py`, ordenados.

    Los `*.py` de la raíz entran para que `app.py` quede DENTRO del censo (el del
    Plan 218 no lo miraba y ahí vive `_startup_sync`). Medido: `app.py` es el único
    archivo de la raíz del backend que llama a un constructor ADO, así que ampliar
    a toda la raíz no cambia los números y vuelve el scanner reusable sobre un
    directorio temporal (F8.4).
    """
    vistos: list[Path] = []
    if raiz.is_dir():
        vistos.extend(sorted(p for p in raiz.glob("*.py") if p.is_file()))
        for sub in ("api", "services"):
            d = raiz / sub
            if d.is_dir():
                vistos.extend(sorted(p for p in d.glob("*.py") if p.is_file()))
    return vistos


def _funciones_con_cuerpo_propio(tree):
    """(nombre, nodos propios) por cada función del módulo, nested incluidas.

    "Propios" = el subárbol de la función MENOS los subárboles de las funciones y
    clases anidadas dentro. Sin esto, `create_child_task` heredaría la llamada a
    `_ado_client_for_ticket` de su nested `_equivalent_task_status` y el censo
    contaría el mismo sitio dos veces.
    """
    import ast as _ast

    defs = [
        n for n in _ast.walk(tree)
        if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef))
    ]
    for fn in defs:
        propios: list = []
        pila = list(fn.body) + list(fn.decorator_list)
        while pila:
            nodo = pila.pop()
            if isinstance(nodo, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
                continue
            propios.append(nodo)
            pila.extend(_ast.iter_child_nodes(nodo))
        yield fn.name, propios


def _literales_str(nodos) -> set[str]:
    import ast as _ast

    return {
        n.value for n in nodos
        if isinstance(n, _ast.Constant) and isinstance(n.value, str)
    }


def _llamadas(nodos) -> set[str]:
    import ast as _ast

    out: set[str] = set()
    for n in nodos:
        if isinstance(n, _ast.Call):
            nombre = _nombre_llamado(n)
            if nombre:
                out.add(nombre)
    return out


def scan_ado_only_sites(raiz: Path | None = None) -> dict:
    """Censo por AST de funciones que construyen cliente ADO sin rutear por tracker.

    ALCANCE (`raiz` default = `_BACKEND`): `*.py` de la raíz + `api/*.py` +
    `services/*.py`. `app.py` va INCLUIDO a propósito: el censo del Plan 218 no lo
    miraba y ahí vive `_startup_sync`. NO clasifica como `ado_only` (ver
    TRACKER_GUARDS); lo captura `ciegos_a_gitlab`.

    EXCLUYE: la familia `services/ado_*.py` (un adaptador ADO tiene derecho a
    serlo) y `services/project_context.py` (define `build_ado_client`).

    CENSA POR REFERENCIA, no por texto: recorre `ast.Call` y acepta tanto
    `ast.Name` (llamada directa) como `ast.Attribute` (llamada por alias de
    módulo, p. ej. `project_context.build_ado_client(...)` en
    `services/completion_sync.py`). Un censo que sólo mirara `ast.Name` daría CERO
    en ese archivo.

    `raiz` es parámetro para que F8.4 pueda apuntarlo a un directorio temporal.
    Devuelve claves ordenadas y deterministas.
    """
    import ast as _ast

    base = _BACKEND if raiz is None else Path(raiz)
    con_seam: set[str] = set()
    gateados: set[str] = set()
    ado_only: set[str] = set()
    ciegos: set[str] = set()

    for path in _archivos_censables(base):
        rel = path.relative_to(base).as_posix()
        if rel.startswith(_ADO_ONLY_EXCLUDED_PREFIXES) or rel in _ADO_ONLY_EXCLUDED_FILES:
            continue
        texto = _read(path)
        if not texto:
            continue
        try:
            tree = _ast.parse(texto)
        except SyntaxError:
            continue

        for nombre, propios in _funciones_con_cuerpo_propio(tree):
            llamadas = _llamadas(propios)
            if not (llamadas & ADO_BUILDERS):
                continue
            clave = f"{rel}::{nombre}"
            if llamadas & PROVIDER_SEAMS:
                con_seam.add(clave)
                continue
            literales = _literales_str(propios)
            discrimina = bool(llamadas & TRACKER_GUARDS) or bool(literales & TRACKER_LITERALS)
            if discrimina:
                gateados.add(clave)
                # Ciego a GitLab: discrimina por tracker pero ni nombra "gitlab" ni
                # delega en el resolvedor canónico (que sí contempla todos).
                if (
                    _LITERAL_GITLAB not in literales
                    and _RESOLVEDOR_CANONICO not in llamadas
                ):
                    ciegos.add(clave)
            else:
                ado_only.add(clave)

    violaciones = sorted(ado_only - set(ADO_ONLY_JUSTIFICADOS))
    return {
        "con_seam": sorted(con_seam),
        "con_seam_count": len(con_seam),
        "gateados": sorted(gateados),
        "gateados_count": len(gateados),
        "ado_only": sorted(ado_only),
        "ado_only_count": len(ado_only),
        "violaciones": violaciones,
        "violaciones_count": len(violaciones),
        "ciegos_a_gitlab": sorted(ciegos),
        "ciegos_count": len(ciegos),
    }


def scan_tracker_type_routing(raiz: Path | None = None) -> list[str]:
    """Funciones que RUTEAN por la columna `<algo>.tracker_type` (no las que la muestran).

    Regla, en dos pasos (data-flow intra-función; NO basta con mirar el `test` de
    un `if`, porque el idioma real separa la lectura de la comparación):

      1. LECTURA — se recolectan los nombres locales asignados desde una expresión
         que contiene un `ast.Attribute` con `attr == "tracker_type"`, incluyendo la
         coalescencia `x.tracker_type or "<default>"`.
      2. RUTEO   — la función se marca si un `ast.Compare` tiene, del lado izquierdo
         o entre sus comparadores, (a) un literal de TRACKER_LITERALS y (b) el
         Attribute directo o alguno de los nombres del paso 1.

    La coalescencia SOLA no cuenta: `(tk.tracker_type or DEF).strip().lower()` usada
    como parte de una clave de identidad es LECTURA legítima (Plan 277,
    `api/tickets.py::_clave` / `_clave_de_padre` / `_crea_ciclo`) y NO debe marcarse.
    Serializar la columna en una respuesta (`d["tracker_type"] = t.tracker_type`)
    tampoco cuenta: mostrarla es legítimo, decidir con ella no.

    EXCLUYE POR ORIGEN: un `.tracker_type` que cuelga directamente de una llamada a
    `resolve_project_context` / `require_project_context` / `get_tracker_provider` /
    `_provider_for_ticket` NO es la columna, es la fuente de verdad ya resuelta
    (p. ej. `api/devops.py::preflight_check_route`). Sin esta exclusión el detector
    devuelve 2 y marca un sitio correcto.

    EXCLUYE POR ARCHIVO: `services/project_context.py` (ahí `ctx.tracker_type` ES la
    verdad resuelta desde el config) y `services/tracker_write_router.py`
    (`target.tracker_type` viene del TrackerTarget resuelto).
    """
    import ast as _ast

    base = _BACKEND if raiz is None else Path(raiz)
    marcadas: set[str] = set()

    def _es_columna(nodo) -> bool:
        """`x.tracker_type` que NO cuelga de una llamada a un origen resuelto."""
        if not (isinstance(nodo, _ast.Attribute) and nodo.attr == "tracker_type"):
            return False
        valor = nodo.value
        if isinstance(valor, _ast.Call):
            return _nombre_llamado(valor) not in _ORIGENES_RESUELTOS
        return True

    def _subnodos(nodo) -> list:
        out: list = []
        pila = [nodo]
        while pila:
            n = pila.pop()
            out.append(n)
            pila.extend(_ast.iter_child_nodes(n))
        return out

    for path in _archivos_censables(base):
        rel = path.relative_to(base).as_posix()
        if rel in _ROUTING_EXCLUDED_FILES:
            continue
        texto = _read(path)
        if not texto:
            continue
        try:
            tree = _ast.parse(texto)
        except SyntaxError:
            continue

        for nombre, propios in _funciones_con_cuerpo_propio(tree):
            # Paso 1 — nombres locales que traen la columna.
            leidos: set[str] = set()
            for nodo in propios:
                valor = getattr(nodo, "value", None)
                if valor is None or not isinstance(
                    nodo, (_ast.Assign, _ast.AnnAssign, _ast.AugAssign)
                ):
                    continue
                if not any(_es_columna(sub) for sub in _subnodos(valor)):
                    continue
                destinos = nodo.targets if isinstance(nodo, _ast.Assign) else [nodo.target]
                for destino in destinos:
                    for sub in _subnodos(destino):
                        if isinstance(sub, _ast.Name):
                            leidos.add(sub.id)

            # Paso 2 — ¿alguna comparación decide con eso contra un literal de tracker?
            for nodo in propios:
                if not isinstance(nodo, _ast.Compare):
                    continue
                operandos = [nodo.left] + list(nodo.comparators)
                planos = [sub for op in operandos for sub in _subnodos(op)]
                hay_literal = any(
                    isinstance(s, _ast.Constant)
                    and isinstance(s.value, str)
                    and s.value in TRACKER_LITERALS
                    for s in planos
                )
                if not hay_literal:
                    continue
                hay_columna = any(
                    _es_columna(s) or (isinstance(s, _ast.Name) and s.id in leidos)
                    for s in planos
                )
                if hay_columna:
                    marcadas.add(f"{rel}::{nombre}")
                    break

    return sorted(marcadas)


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
