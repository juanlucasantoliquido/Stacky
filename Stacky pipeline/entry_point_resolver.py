"""
entry_point_resolver.py — S-03: Entry Point Resolver: Form ASPX / Batch Job → Handler inicial.

Dado el nombre de un Form ASPX o un Batch Job mencionado en el ticket,
encuentra el metodo handler inicial de ejecucion:
  - Form ASPX → Page_Load, btnX_Click, OnInit, etc.
  - Batch Job → Execute(), Run(), Main(), Process()

Esto da a PM y DEV el punto de entrada exacto del flujo afectado,
eliminando la busqueda manual en el ASPX code-behind.

Uso:
    from entry_point_resolver import EntryPointResolver
    resolver = EntryPointResolver(workspace_root)
    result = resolver.resolve("FrmPedidos.aspx")
    # result.entry_points  → lista de EntryPoint ordenados por prioridad
    # result.markdown       → bloque para inyectar en prompt PM
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent

# Handlers de alta prioridad para WebForms
_WEBFORM_HANDLERS = [
    "Page_Load", "Page_Init", "Page_PreRender",
    "btnGuardar_Click", "btnBuscar_Click", "btnEliminar_Click",
    "btnNuevo_Click", "btnActualizar_Click", "btnProcesar_Click",
    "GridView_RowCommand", "GridView_RowEditing",
    "ddl_SelectedIndexChanged", "txt_TextChanged",
]

# Handlers de alta prioridad para Batch Jobs
_BATCH_HANDLERS = [
    "Execute", "Run", "Process", "Main", "EjecutarProceso",
    "ProcesarRegistros", "GenerarReporte",
]


@dataclass
class EntryPoint:
    """Un punto de entrada encontrado en el codebase."""
    file_path:   str = ""
    class_name:  str = ""
    method_name: str = ""
    line_number: int = 0
    signature:   str = ""    # firma completa del metodo
    priority:    int = 0     # 1=alta, 2=media, 3=baja
    entry_type:  str = ""    # "webform_handler", "batch_entry", "override"


@dataclass
class ResolveResult:
    """Resultado de la resolucion de un entry point."""
    query:        str = ""
    found:        bool = False
    entry_points: list = field(default_factory=list)
    source_file:  str = ""    # archivo .aspx o .aspx.cs encontrado
    markdown:     str = ""


class EntryPointResolver:
    """
    Resuelve el entry point de Forms ASPX y Batch Jobs desde el nombre.
    """

    def __init__(self, workspace_root: str = None):
        self._workspace = Path(workspace_root) if workspace_root else BASE_DIR.parent.parent

    def resolve(self, name: str) -> ResolveResult:
        """
        Resuelve el entry point para un Form o Batch dado su nombre.
        name puede ser: "FrmPedidos", "FrmPedidos.aspx", "BatchProcesarPedidos"
        """
        result = ResolveResult(query=name)

        # Normalizar nombre
        base_name = Path(name).stem.replace(".aspx", "")

        # Detectar tipo
        is_form  = "frm" in base_name.lower() or name.lower().endswith(".aspx")
        is_batch = "batch" in base_name.lower() or "proceso" in base_name.lower()

        # Buscar archivo fuente
        source_file = self._find_source_file(base_name)
        if source_file:
            result.source_file = str(source_file)
            result.found = True

        # Buscar handlers
        entry_points = []
        if source_file:
            entry_points = self._extract_handlers(source_file, is_batch)
        else:
            # Buscar en todo el trunk si no encontramos el archivo exacto
            entry_points = self._search_trunk(base_name, is_batch)

        if entry_points:
            result.found = True
            result.entry_points = entry_points

        result.markdown = self._build_markdown(result)
        return result

    def resolve_from_ticket(self, inc_content: str) -> Optional[ResolveResult]:
        """
        Extrae automáticamente el Form o Batch mencionado en el ticket
        y resuelve su entry point.
        """
        # Buscar menciones de Forms y Batches
        form_pattern  = re.compile(r"Frm\w+|frm\w+", re.IGNORECASE)
        batch_pattern = re.compile(r"Batch\w+|batch\w+|Proceso\w+", re.IGNORECASE)
        aspx_pattern  = re.compile(r"[\w.]+\.aspx", re.IGNORECASE)

        candidates = []
        for match in form_pattern.finditer(inc_content):
            candidates.append(match.group(0))
        for match in aspx_pattern.finditer(inc_content):
            candidates.append(match.group(0))
        for match in batch_pattern.finditer(inc_content):
            candidates.append(match.group(0))

        if not candidates:
            return None

        # Tomar el candidato mas frecuente
        from collections import Counter
        most_common = Counter(candidates).most_common(1)[0][0]
        return self.resolve(most_common)

    # ── Privados ─────────────────────────────────────────────────────────────

    def _find_source_file(self, base_name: str) -> Optional[Path]:
        """Busca el archivo .aspx.cs o .cs correspondiente."""
        for pattern in (
            f"{base_name}.aspx.cs",
            f"{base_name}.aspx.vb",
            f"{base_name}.cs",
            f"{base_name}.vb",
        ):
            matches = list(self._workspace.rglob(pattern))
            if matches:
                return matches[0]

        # Busqueda case-insensitive
        lower = base_name.lower()
        for fpath in self._workspace.rglob("*.cs"):
            if fpath.stem.lower() == lower or fpath.name.lower() == f"{lower}.aspx.cs":
                return fpath
        return None

    def _extract_handlers(self, source_file: Path, is_batch: bool) -> list:
        """Extrae handlers del archivo fuente."""
        handlers_priority = _BATCH_HANDLERS if is_batch else _WEBFORM_HANDLERS
        method_pattern = re.compile(
            r"(?P<access>public|private|protected|internal)?\s*"
            r"(?P<modifier>(?:static|override|virtual|async)\s+)*"
            r"(?P<return>[\w<>\[\]]+)\s+"
            r"(?P<name>\w+)\s*"
            r"\((?P<params>[^)]*)\)"
        )

        try:
            lines = source_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            return []

        try:
            rel_path = str(source_file.relative_to(self._workspace))
        except ValueError:
            rel_path = source_file.name

        entries = []
        class_name = self._extract_class_name(lines)

        for i, line in enumerate(lines):
            match = method_pattern.search(line)
            if not match:
                continue
            method_name = match.group("name")

            # Calcular prioridad
            if method_name in handlers_priority:
                priority = 1
                etype    = "webform_handler" if not is_batch else "batch_entry"
            elif any(h.lower() in method_name.lower() for h in ["click", "load", "init"]):
                priority = 2
                etype    = "webform_handler"
            elif re.match(r"^(On|Handle|Process|Execute)", method_name):
                priority = 2
                etype    = "override"
            else:
                continue  # Ignorar metodos sin relevancia de entry point

            entries.append(EntryPoint(
                file_path   = rel_path,
                class_name  = class_name,
                method_name = method_name,
                line_number = i + 1,
                signature   = line.strip()[:100],
                priority    = priority,
                entry_type  = etype,
            ))

        # Ordenar por prioridad, luego por posicion en archivo
        entries.sort(key=lambda e: (e.priority, e.line_number))
        return entries[:10]

    def _search_trunk(self, base_name: str, is_batch: bool) -> list:
        """Busqueda amplia en el trunk cuando no se encontro el archivo exacto."""
        pattern = re.compile(
            rf"(?:public|private|protected)\s+.*?\s+(\w*(?:{re.escape(base_name)}\w*|"
            rf"Page_Load|Execute|Run))\s*\(",
            re.IGNORECASE,
        )
        entries = []
        for fpath in list(self._workspace.rglob("*.cs"))[:200]:
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
                if base_name.lower() not in content.lower():
                    continue
                for i, line in enumerate(content.splitlines()):
                    m = pattern.search(line)
                    if m:
                        try:
                            rel = str(fpath.relative_to(self._workspace))
                        except ValueError:
                            rel = fpath.name
                        entries.append(EntryPoint(
                            file_path   = rel,
                            method_name = m.group(1),
                            line_number = i + 1,
                            signature   = line.strip()[:100],
                            priority    = 2,
                        ))
                        if len(entries) >= 5:
                            break
            except Exception:
                pass
            if len(entries) >= 5:
                break
        return entries

    def _extract_class_name(self, lines: list) -> str:
        pattern = re.compile(r"(?:public|internal)\s+(?:partial\s+)?class\s+(\w+)")
        for line in lines:
            m = pattern.search(line)
            if m:
                return m.group(1)
        return ""

    def _build_markdown(self, result: ResolveResult) -> str:
        lines = [
            "## Entry Point Resolver",
            "",
            f"**Componente:** `{result.query}`",
        ]

        if result.source_file:
            lines.append(f"**Archivo fuente:** `{result.source_file}`")

        if not result.found or not result.entry_points:
            lines.append("")
            lines.append("_No se encontraron entry points para este componente._")
            return "\n".join(lines)

        lines += ["", "### Handlers/Entry Points Identificados", ""]
        lines.append("| Metodo | Linea | Tipo | Prioridad |")
        lines.append("|--------|-------|------|-----------|")
        for ep in result.entry_points[:6]:
            prio_str = "🔴 Alta" if ep.priority == 1 else "🟡 Media" if ep.priority == 2 else "🟢 Baja"
            lines.append(
                f"| `{ep.method_name}` | {ep.line_number} | {ep.entry_type} | {prio_str} |"
            )

        if result.entry_points:
            primary = result.entry_points[0]
            lines += [
                "",
                f"**Punto de entrada principal:** `{primary.class_name}.{primary.method_name}()` "
                f"— [{Path(primary.file_path).name}:{primary.line_number}]",
            ]

        return "\n".join(lines)
