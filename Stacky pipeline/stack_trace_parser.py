"""
stack_trace_parser.py — S-01: Parser de Stack Traces .NET → Archivo/Método exacto.

Extrae informacion estructurada de stack traces .NET pegados en tickets:
  - Archivo exacto (con ruta relativa al trunk)
  - Nombre del método y firma
  - Numero de linea
  - Namespace / clase completa

Esto elimina la busqueda manual: PM recibe inmediatamente el punto exacto
de falla en vez de tener que inferirlo desde la descripcion del error.

Uso:
    from stack_trace_parser import StackTraceParser
    parser = StackTraceParser(workspace_root)
    result = parser.parse(inc_content)
    # result.frames     → lista de FrameInfo ordenadas por relevancia
    # result.primary    → frame mas probable del bug (no es Framework/System)
    # result.markdown   → bloque Markdown para inyectar en prompt PM
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent


@dataclass
class FrameInfo:
    """Informacion de un frame del stack trace."""
    raw_line:    str
    namespace:   str = ""
    class_name:  str = ""
    method_name: str = ""
    file_path:   str = ""          # ruta encontrada en disco (relativa al trunk)
    line_number: int = 0
    is_system:   bool = False       # True si es .NET Framework / System.*
    exists_on_disk: bool = False    # True si se encontro el archivo fisicamente


@dataclass
class ParseResult:
    """Resultado completo del parsing de un stack trace."""
    has_stack_trace: bool = False
    frames: list = field(default_factory=list)
    primary: Optional[FrameInfo] = None
    error_message: str = ""
    markdown: str = ""


class StackTraceParser:
    """
    Parsea stack traces .NET desde el contenido de un ticket INC.
    Busca los archivos en el workspace para confirmar existencia.
    """

    # Patron .NET: "   en Namespace.Class.Method(params) en C:\...\file.cs:linea N"
    _FRAME_PATTERN = re.compile(
        r"\s+(?:en|at)\s+"
        r"([\w.<>]+(?:\.[\w.<>]+)*)"  # namespace.class.method
        r"\(([^)]*)\)"                # parametros
        r"(?:\s+(?:en|in)\s+"
        r"([^\n:]+\.(?:cs|vb|aspx\.cs|aspx))"  # archivo
        r":(?:linea|line)\s+(\d+))?", # numero de linea (opcional)
        re.IGNORECASE,
    )

    # Patron de linea de error (antes del stack)
    _ERROR_PATTERN = re.compile(
        r"(?:Exception|Error|System\.\w+Exception)[:\s].*",
        re.IGNORECASE,
    )

    # Prefijos de namespace que indican frame de sistema (no del proyecto)
    _SYSTEM_PREFIXES = (
        "System.", "Microsoft.", "mscorlib.", "Newtonsoft.",
        "Oracle.", "log4net.", "NUnit.", "NHibernate.",
    )

    def __init__(self, workspace_root: str = None):
        self._workspace = Path(workspace_root) if workspace_root else BASE_DIR.parent.parent

    def parse(self, text: str) -> ParseResult:
        """
        Parsea el texto del ticket y extrae frames del stack trace.
        """
        result = ParseResult()

        # Buscar linea de error
        error_match = self._ERROR_PATTERN.search(text)
        if error_match:
            result.error_message = error_match.group(0).strip()[:200]

        # Buscar frames
        frames = []
        for match in self._FRAME_PATTERN.finditer(text):
            full_name   = match.group(1)
            # params    = match.group(2)
            file_hint   = match.group(3) or ""
            line_str    = match.group(4) or "0"

            parts      = full_name.rsplit(".", 2)
            if len(parts) >= 2:
                namespace  = ".".join(parts[:-2]) if len(parts) >= 3 else ""
                class_name = parts[-2] if len(parts) >= 2 else ""
                method     = parts[-1]
            else:
                namespace  = ""
                class_name = ""
                method     = full_name

            is_sys = any(full_name.startswith(p) for p in self._SYSTEM_PREFIXES)

            frame = FrameInfo(
                raw_line    = match.group(0).strip(),
                namespace   = namespace,
                class_name  = class_name,
                method_name = method,
                file_path   = self._resolve_file(file_hint, class_name),
                line_number = int(line_str) if line_str.isdigit() else 0,
                is_system   = is_sys,
            )
            frame.exists_on_disk = bool(frame.file_path)
            frames.append(frame)

        if frames:
            result.has_stack_trace = True
            result.frames = frames
            # El frame primario es el primer frame no-sistema con archivo conocido
            non_sys = [f for f in frames if not f.is_system]
            if non_sys:
                result.primary = non_sys[0]
            elif frames:
                result.primary = frames[0]
            result.markdown = self._build_markdown(result)

        return result

    def _resolve_file(self, file_hint: str, class_name: str) -> str:
        """
        Intenta encontrar el archivo en el workspace.
        Primero por la ruta exacta del stack trace, luego por nombre de clase.
        """
        if file_hint:
            fname = Path(file_hint).name
            # Busqueda por nombre de archivo
            matches = list(self._workspace.rglob(fname))
            if matches:
                try:
                    return str(matches[0].relative_to(self._workspace))
                except ValueError:
                    return str(matches[0])

        if class_name:
            # Buscar por nombre de clase (archivo .cs con mismo nombre)
            for ext in (".cs", ".aspx.cs", ".vb"):
                matches = list(self._workspace.rglob(f"{class_name}{ext}"))
                if matches:
                    try:
                        return str(matches[0].relative_to(self._workspace))
                    except ValueError:
                        return str(matches[0])

        return ""

    def _build_markdown(self, result: ParseResult) -> str:
        lines = ["## Stack Trace Analizado por Stacky", ""]

        if result.error_message:
            lines.append(f"**Error:** `{result.error_message}`")
            lines.append("")

        if result.primary:
            p = result.primary
            lines.append("### Punto de Falla Identificado")
            lines.append("")
            lines.append(f"- **Clase:** `{p.namespace}.{p.class_name}` " if p.namespace else f"- **Clase:** `{p.class_name}`")
            lines.append(f"- **Método:** `{p.method_name}()`")
            if p.file_path:
                link = f"`{p.file_path}`"
                if p.line_number:
                    link += f" — línea {p.line_number}"
                lines.append(f"- **Archivo:** {link}")
                lines.append(f"- **Existe en trunk:** {'✅ Si' if p.exists_on_disk else '❌ No encontrado'}")
            lines.append("")

        non_sys = [f for f in result.frames if not f.is_system][:5]
        if len(non_sys) > 1:
            lines.append("### Frames del Proyecto (excluye System.*)")
            lines.append("")
            lines.append("| Clase | Método | Archivo | Línea |")
            lines.append("|-------|--------|---------|-------|")
            for f in non_sys:
                fname = Path(f.file_path).name if f.file_path else "—"
                lines.append(f"| `{f.class_name}` | `{f.method_name}` | `{fname}` | {f.line_number or '—'} |")

        return "\n".join(lines)
