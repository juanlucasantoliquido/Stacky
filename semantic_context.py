"""
semantic_context.py — E-06: Contexto Semántico de Código (AST-lite sin tree-sitter).

Extrae contexto semántico rico de archivos C# y ASPX usando regex-based parsing:
  - Declaraciones de clase y sus métodos
  - Métodos que contienen código relevante al ticket
  - Firmas de métodos (parámetros, tipos de retorno)
  - Propiedades y campos importantes
  - Herencias e interfaces implementadas

Este contexto es más útil para el DEV que solo el texto raw del archivo,
porque le muestra exactamente el método a modificar con su contexto inmediato.

Uso:
    from semantic_context import SemanticContextExtractor
    sce = SemanticContextExtractor()
    context = sce.extract_for_ticket(ticket_folder, ticket_id, workspace_root)
    section = sce.format_semantic_section(context)
"""

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("stacky.semantic_context")

_MAX_METHOD_LINES = 60
_MAX_METHODS_PER_FILE = 5
_MAX_FILES = 8
_SKIP_DIRS = {"bin", "obj", ".vs", ".git", "packages"}


@dataclass
class MethodInfo:
    name:        str
    signature:   str    # "public void DoSomething(string param)"
    body_lines:  list[str] = field(default_factory=list)
    line_number: int = 0
    is_relevant: bool = False


@dataclass
class ClassInfo:
    name:       str
    namespace:  str
    file_path:  str
    base_class: str = ""
    interfaces: list[str] = field(default_factory=list)
    methods:    list[MethodInfo] = field(default_factory=list)


@dataclass
class SemanticContext:
    classes:   list[ClassInfo]
    symbols_found: list[str]
    query_used:    str


class SemanticContextExtractor:
    """
    Extrae contexto semántico de código C#/VB.NET usando análisis regex.
    Sin dependencias externas.
    """

    # ── API pública ───────────────────────────────────────────────────────

    def extract_for_ticket(self, ticket_folder: str, ticket_id: str,
                            workspace_root: str) -> SemanticContext:
        """
        Extrae contexto semántico de los archivos relevantes al ticket.
        """
        # Obtener símbolos del ticket
        symbols = self._get_ticket_symbols(ticket_folder, ticket_id)
        if not symbols:
            return SemanticContext(classes=[], symbols_found=[], query_used="")

        # Encontrar archivos relevantes
        relevant_files = self._find_relevant_files(workspace_root, symbols)

        # Extraer clases y métodos de los archivos relevantes
        classes = []
        for fpath in relevant_files[:_MAX_FILES]:
            try:
                content = Path(fpath).read_text(encoding="utf-8", errors="replace")
                cls = self._parse_csharp_file(content, fpath, symbols)
                if cls:
                    classes.append(cls)
            except Exception as e:
                logger.debug("[SEMANTIC] Error parseando %s: %s", fpath, e)

        return SemanticContext(
            classes=classes,
            symbols_found=symbols,
            query_used=" ".join(symbols[:5]),
        )

    def format_semantic_section(self, ctx: SemanticContext) -> str:
        """Formatea el contexto semántico como sección Markdown para prompts."""
        if not ctx.classes:
            return ""

        lines = [
            "",
            "---",
            "",
            "## Contexto Semántico del Código",
            "",
            "_Clases y métodos relevantes extraídos del codebase._",
            "",
        ]

        for cls in ctx.classes:
            rel_path = os.path.basename(cls.file_path)
            lines.append(f"### `{cls.name}` — `{rel_path}`")
            lines.append("")
            if cls.namespace:
                lines.append(f"**Namespace:** `{cls.namespace}`")
            if cls.base_class:
                lines.append(f"**Hereda de:** `{cls.base_class}`")
            if cls.interfaces:
                lines.append(f"**Implementa:** {', '.join(f'`{i}`' for i in cls.interfaces)}")
            lines.append("")

            relevant_methods = [m for m in cls.methods if m.is_relevant]
            other_methods    = [m for m in cls.methods if not m.is_relevant]

            if relevant_methods:
                lines.append("**Métodos más relevantes al ticket:**")
                lines.append("")
                for m in relevant_methods[:3]:
                    lines.append(f"```csharp")
                    lines.append(f"// Línea {m.line_number}")
                    lines.append(m.signature)
                    lines.append("{")
                    for body_line in m.body_lines[:20]:
                        lines.append(f"    {body_line}")
                    if len(m.body_lines) > 20:
                        lines.append(f"    // ... ({len(m.body_lines)} líneas en total)")
                    lines.append("}")
                    lines.append("```")
                    lines.append("")

            if other_methods:
                sigs = [m.signature for m in other_methods[:6]]
                lines.append("**Otros métodos en la clase:**")
                for sig in sigs:
                    lines.append(f"- `{sig}`")
                lines.append("")

        return "\n".join(lines)

    # ── Internals ─────────────────────────────────────────────────────────

    def _get_ticket_symbols(self, ticket_folder: str, ticket_id: str) -> list[str]:
        """Extrae símbolos (clases, métodos) del ticket."""
        symbols: set[str] = set()

        for fname in ["ARQUITECTURA_SOLUCION.md", "ANALISIS_TECNICO.md",
                      f"INC-{ticket_id}.md"]:
            fpath = os.path.join(ticket_folder, fname)
            if not os.path.exists(fpath):
                continue
            try:
                content = Path(fpath).read_text(encoding="utf-8", errors="replace")
                # Clases y métodos PascalCase
                for m in re.finditer(r'\b([A-Z][a-zA-Z0-9]{3,})\b', content):
                    sym = m.group(1)
                    if sym not in {"True", "False", "None", "String", "List"}:
                        symbols.add(sym)
                # DAL/BLL/Frm patterns
                for m in re.finditer(r'\b((?:DAL|BLL|Frm)_?\w{3,})\b', content,
                                     re.IGNORECASE):
                    symbols.add(m.group(1))
            except Exception:
                pass

        return list(symbols)[:20]

    def _find_relevant_files(self, workspace_root: str,
                              symbols: list[str]) -> list[str]:
        """Encuentra archivos que contienen los símbolos buscados."""
        if not workspace_root or not os.path.isdir(workspace_root):
            return []

        file_scores: dict[str, int] = {}
        sym_lower   = [s.lower() for s in symbols]

        for root, dirs, files in os.walk(workspace_root):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for fname in files:
                if not fname.endswith((".cs", ".aspx.cs")):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    content_lower = Path(fpath).read_text(
                        encoding="utf-8", errors="replace")[:8000].lower()
                    score = sum(content_lower.count(sym) for sym in sym_lower)
                    if score > 0:
                        file_scores[fpath] = score
                except Exception:
                    pass

        sorted_files = sorted(file_scores, key=lambda k: -file_scores[k])
        return sorted_files[:_MAX_FILES]

    def _parse_csharp_file(self, content: str, file_path: str,
                            symbols: list[str]) -> ClassInfo | None:
        """
        Parsea un archivo C# extrayendo clase, métodos y su contexto.
        """
        lines = content.splitlines()

        # Extraer namespace
        ns_match = re.search(r'^namespace\s+([\w.]+)', content, re.MULTILINE)
        namespace = ns_match.group(1) if ns_match else ""

        # Extraer clase principal
        cls_match = re.search(
            r'(?:public|internal|private)?\s*(?:partial\s+)?class\s+(\w+)'
            r'(?:\s*:\s*([^{]+))?',
            content
        )
        if not cls_match:
            return None

        class_name   = cls_match.group(1)
        inheritance  = cls_match.group(2) or ""
        base_class   = ""
        interfaces   = []
        if inheritance:
            parts = [p.strip() for p in inheritance.split(",")]
            for p in parts:
                if p.startswith("I") and len(p) > 2 and p[1].isupper():
                    interfaces.append(p)
                elif p:
                    base_class = p if not base_class else base_class

        # Extraer métodos
        method_pattern = re.compile(
            r'(?:public|private|protected|internal|override|virtual|static|async)'
            r'[\s\w<>[\],?]*'
            r'\s+(\w+)\s*\(([^)]*)\)\s*(?:where[^{]*)?\s*\{',
            re.MULTILINE
        )

        methods = []
        sym_lower = {s.lower() for s in symbols}

        for m in method_pattern.finditer(content):
            method_name = m.group(1)
            if method_name in {"if", "while", "for", "foreach", "switch",
                                "using", "lock", "try"}:
                continue

            line_num = content[:m.start()].count("\n") + 1
            sig_start = m.start()
            # Reconstruir firma desde la línea
            sig_line = lines[line_num - 1].strip() if line_num <= len(lines) else m.group(0)
            sig_line = re.sub(r'\s*\{.*', '', sig_line).strip()

            # Extraer body (hasta el closing brace al mismo nivel)
            body_start = m.end()
            body_lines = self._extract_method_body(content, body_start, _MAX_METHOD_LINES)

            body_text = " ".join(body_lines).lower()
            is_relevant = (
                method_name.lower() in sym_lower or
                any(sym in body_text for sym in sym_lower if len(sym) >= 5)
            )

            methods.append(MethodInfo(
                name=method_name,
                signature=sig_line,
                body_lines=body_lines,
                line_number=line_num,
                is_relevant=is_relevant,
            ))

        # Ordenar: relevantes primero
        methods.sort(key=lambda x: (not x.is_relevant, x.line_number))

        return ClassInfo(
            name=class_name,
            namespace=namespace,
            file_path=file_path,
            base_class=base_class,
            interfaces=interfaces,
            methods=methods[:_MAX_METHODS_PER_FILE * 2],
        )

    @staticmethod
    def _extract_method_body(content: str, start: int,
                              max_lines: int) -> list[str]:
        """Extrae el body de un método hasta el closing brace balanceado."""
        depth  = 1
        lines  = []
        i      = start
        length = len(content)
        current_line = []

        while i < length and depth > 0 and len(lines) < max_lines:
            ch = content[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            elif ch == "\n":
                line = "".join(current_line).strip()
                if line:
                    lines.append(line)
                current_line = []
                i += 1
                continue
            current_line.append(ch)
            i += 1

        return lines
