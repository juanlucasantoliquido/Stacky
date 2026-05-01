"""
blast_radius_analyzer.py — G-05: Blast Radius Analysis (Mapa de Impacto).

Analiza estáticamente qué otros archivos/clases podrían verse afectados
por los cambios propuestos en ARQUITECTURA_SOLUCION.md, sin ejecutar el código.

Estrategia:
  1. Identifica clases/métodos que se van a modificar
  2. Busca en el workspace qué otros archivos los referencian (grep de texto)
  3. Clasifica el impacto: DIRECTO (usa la clase) | INDIRECTO (cadena de 2 saltos)
  4. Genera BLAST_RADIUS.md con mapa visual del impacto

Sin dependencias externas — solo os.walk + re.

Uso:
    from blast_radius_analyzer import analyze_blast_radius
    result = analyze_blast_radius(ticket_folder, ticket_id, workspace_root)
"""

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("stacky.blast_radius")

# Extensiones de código fuente a analizar
_CODE_EXTS = {".cs", ".aspx", ".aspx.cs", ".vb", ".sql"}
_SKIP_DIRS  = {"bin", "obj", "node_modules", ".git", "packages",
               ".vs", "TestResults"}

# Cap de archivos a indexar para evitar explosión en repos grandes
_MAX_INDEX_FILES = 3000
_MAX_REFS_PER_SYMBOL = 50


@dataclass
class ImpactedFile:
    path:        str
    impact:      str      # "direct" | "indirect"
    references:  list[str] = field(default_factory=list)  # símbolos que referencia
    ref_count:   int = 0


@dataclass
class BlastRadius:
    ticket_id:       str
    symbols_changed: list[str]
    direct:          list[ImpactedFile]
    indirect:        list[ImpactedFile]
    total_impacted:  int
    analyzed_at:     str


def analyze_blast_radius(ticket_folder: str, ticket_id: str,
                         workspace_root: str,
                         max_depth: int = 2) -> BlastRadius | None:
    """
    Analiza el blast radius del ticket y genera BLAST_RADIUS.md.
    max_depth: 1=solo directo, 2=directo+indirecto.
    """
    if not workspace_root or not os.path.isdir(workspace_root):
        return None

    # 1. Extraer símbolos (clases/métodos) que cambia este ticket
    symbols = _extract_changed_symbols(ticket_folder)
    if not symbols:
        logger.info("[BLAST] Ticket #%s: no se encontraron símbolos a analizar", ticket_id)
        return None

    logger.info("[BLAST] Ticket #%s: analizando %d símbolos — indexando workspace...",
                ticket_id, len(symbols))

    # 2. Indexar workspace (path → contenido tokenizado)
    index = _build_workspace_index(workspace_root)
    logger.info("[BLAST] %d archivos indexados", len(index))

    # 3. Buscar referencias directas
    direct_map: dict[str, ImpactedFile] = {}
    for sym in symbols:
        for fpath, content in index.items():
            if sym.lower() in content.lower():
                if fpath not in direct_map:
                    direct_map[fpath] = ImpactedFile(path=fpath, impact="direct")
                direct_map[fpath].references.append(sym)
                direct_map[fpath].ref_count += 1
                if direct_map[fpath].ref_count >= _MAX_REFS_PER_SYMBOL:
                    break

    # Excluir los propios archivos del ticket de direct
    ticket_files = _get_ticket_files_set(ticket_folder)
    direct_clean = {k: v for k, v in direct_map.items()
                    if not any(tf in k for tf in ticket_files)}

    # 4. Buscar referencias indirectas (archivos que referencian los directos)
    indirect_map: dict[str, ImpactedFile] = {}
    if max_depth >= 2:
        direct_classes = {_extract_class_name(p) for p in direct_clean if _extract_class_name(p)}
        for sym in direct_classes:
            for fpath, content in index.items():
                if fpath in direct_clean or fpath in ticket_files:
                    continue
                if sym.lower() in content.lower():
                    if fpath not in indirect_map:
                        indirect_map[fpath] = ImpactedFile(path=fpath, impact="indirect")
                    indirect_map[fpath].references.append(sym)
                    indirect_map[fpath].ref_count += 1

    direct_list   = sorted(direct_clean.values(),  key=lambda x: -x.ref_count)[:30]
    indirect_list = sorted(indirect_map.values(),  key=lambda x: -x.ref_count)[:20]

    result = BlastRadius(
        ticket_id=ticket_id,
        symbols_changed=symbols,
        direct=direct_list,
        indirect=indirect_list,
        total_impacted=len(direct_list) + len(indirect_list),
        analyzed_at=datetime.now().isoformat(),
    )

    _write_blast_radius_report(ticket_folder, result)
    logger.info("[BLAST] Ticket #%s: %d directo, %d indirecto",
                ticket_id, len(direct_list), len(indirect_list))
    return result


# ── Internals ─────────────────────────────────────────────────────────────────

def _extract_changed_symbols(ticket_folder: str) -> list[str]:
    """Extrae nombres de clases/métodos que se modificarán."""
    symbols = set()

    for fname in ["ARQUITECTURA_SOLUCION.md", "ANALISIS_TECNICO.md", "DEV_COMPLETADO.md"]:
        fpath = os.path.join(ticket_folder, fname)
        if not os.path.exists(fpath):
            continue
        try:
            content = Path(fpath).read_text(encoding="utf-8", errors="replace")
            # Clases: PascalCase de 4+ chars
            for m in re.finditer(r'\b([A-Z][a-zA-Z]{3,}(?:DAL|BLL|Frm|Manager|Service|Helper|Controller)?)\b',
                                  content):
                sym = m.group(1)
                if len(sym) >= 4 and sym not in {"True", "False", "None", "This"}:
                    symbols.add(sym)
            # DAL/BLL patterns
            for m in re.finditer(r'\b((?:DAL|BLL|Frm)_?\w{3,})\b', content, re.IGNORECASE):
                symbols.add(m.group(1))
            # Métodos: verbPascal
            for m in re.finditer(r'\b((?:Get|Set|Load|Save|Update|Delete|Insert|Create|'
                                  r'Validate|Check|Process|Execute|Run|Build|Generate|'
                                  r'Obtener|Guardar|Cargar|Actualizar|Eliminar)[A-Z]\w{3,})\b',
                                  content):
                symbols.add(m.group(1))
        except Exception:
            pass

    # Filtrar símbolos muy genéricos
    _GENERIC = {"String", "List", "Dictionary", "Object", "Boolean", "Integer",
                "DateTime", "Exception", "Response", "Request"}
    return [s for s in symbols if s not in _GENERIC][:40]


def _build_workspace_index(workspace_root: str) -> dict[str, str]:
    """Indexa archivos de código del workspace (path → contenido)."""
    index: dict[str, str] = {}
    count = 0
    for root, dirs, files in os.walk(workspace_root):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        if count >= _MAX_INDEX_FILES:
            break
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in _CODE_EXTS:
                continue
            fpath = os.path.join(root, fname)
            try:
                content = Path(fpath).read_text(encoding="utf-8",
                                                 errors="replace")[:8000]
                rel = os.path.relpath(fpath, workspace_root).replace("\\", "/")
                index[rel] = content
                count += 1
                if count >= _MAX_INDEX_FILES:
                    break
            except Exception:
                pass
    return index


def _get_ticket_files_set(ticket_folder: str) -> set[str]:
    """Retorna set de nombres de archivo mencionados en el ticket."""
    files: set[str] = set()
    for fname in ["ARQUITECTURA_SOLUCION.md", "DEV_COMPLETADO.md", "GIT_CHANGES.md"]:
        fpath = os.path.join(ticket_folder, fname)
        if not os.path.exists(fpath):
            continue
        try:
            content = Path(fpath).read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r'([\w]+\.(?:cs|aspx\.cs|aspx|vb|sql))', content,
                                  re.IGNORECASE):
                files.add(m.group(1).lower())
        except Exception:
            pass
    return files


def _extract_class_name(file_path: str) -> str:
    """Intenta extraer el nombre de clase del nombre de archivo."""
    base = os.path.splitext(os.path.basename(file_path))[0]
    base = re.sub(r'\.aspx$', '', base, flags=re.IGNORECASE)
    return base if len(base) >= 3 else ""


def _write_blast_radius_report(ticket_folder: str, br: BlastRadius) -> None:
    """Genera BLAST_RADIUS.md con el mapa de impacto."""
    risk = "🔴 ALTO" if br.total_impacted > 20 else \
           "🟡 MEDIO" if br.total_impacted > 5 else "🟢 BAJO"

    lines = [
        f"# Blast Radius Analysis — Ticket #{br.ticket_id}",
        "",
        f"> Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"> Riesgo estimado: **{risk}** — {br.total_impacted} archivos potencialmente afectados",
        "",
        "---",
        "",
        f"## Símbolos modificados ({len(br.symbols_changed)})",
        "",
        ", ".join(f"`{s}`" for s in br.symbols_changed[:20]),
        "",
        "---",
        "",
        f"## Impacto Directo ({len(br.direct)} archivos)",
        "",
        "_Archivos que referencian directamente las clases/métodos modificados._",
        "",
        "| Archivo | Referencias | Símbolos |",
        "|---------|-------------|---------|",
    ]
    for f in br.direct[:20]:
        syms = ", ".join(f.references[:3])
        lines.append(f"| `{f.path}` | {f.ref_count} | {syms} |")

    if br.indirect:
        lines += [
            "",
            "---",
            "",
            f"## Impacto Indirecto ({len(br.indirect)} archivos)",
            "",
            "_Archivos que referencian los archivos de impacto directo._",
            "",
            "| Archivo | Referencias | Símbolos |",
            "|---------|-------------|---------|",
        ]
        for f in br.indirect[:15]:
            syms = ", ".join(f.references[:3])
            lines.append(f"| `{f.path}` | {f.ref_count} | {syms} |")

    lines += [
        "",
        "---",
        "",
        "## Recomendaciones",
        "",
        f"- {'Ejecutar regresión completa del módulo' if br.total_impacted > 15 else 'Smoke test en los archivos de impacto directo'}",
        "- Revisar los archivos de impacto directo después del fix",
        "- Coordinar con el equipo si hay archivos de otros módulos afectados",
        "",
        "_Análisis estático generado por Stacky Blast Radius Analyzer._",
    ]

    report_path = os.path.join(ticket_folder, "BLAST_RADIUS.md")
    try:
        Path(report_path).write_text("\n".join(lines), encoding="utf-8")
    except Exception as e:
        logger.error("[BLAST] Error escribiendo BLAST_RADIUS.md: %s", e)
