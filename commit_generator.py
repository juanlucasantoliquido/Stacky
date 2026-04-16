"""
commit_generator.py — Generación automática de mensajes de commit SVN post-QA.

Analiza DEV_COMPLETADO.md, TESTER_COMPLETADO.md y los archivos PM del ticket
para construir un mensaje de commit SVN siguiendo las convenciones del proyecto
(tipo de cambio, referencia al ticket Mantis, archivos modificados, veredicto QA).

El mensaje se guarda en COMMIT_MESSAGE.txt en la carpeta del ticket.
El developer solo tiene que copiarlo (o se puede usar directamente con svn commit -F).

Uso:
    from commit_generator import generate_commit_message
    path = generate_commit_message(ticket_folder, ticket_id, project_name)
"""

import os
import re
from datetime import datetime
from pathlib import Path

# ── Convenciones de commit por tipo de cambio ────────────────────────────────

_TYPE_KEYWORDS = {
    "BUG":    ["error", "bug", "falla", "crash", "excepción", "null", "nullreference",
               "object reference", "corregir", "fix", "arreglar"],
    "FEAT":   ["nueva funcionalidad", "feature", "agregar", "implementar", "nuevo módulo",
               "nueva pantalla", "nueva opción"],
    "PERF":   ["rendimiento", "performance", "lentitud", "timeout", "optimizar",
               "índice", "query lenta"],
    "VALID":  ["validación", "validar", "mensajes", "ridioma", "mensaje al usuario"],
    "REFACT": ["refactor", "refactorización", "reorganizar", "simplificar"],
    "CONFIG": ["configuración", "config", "parámetro", "setting"],
}

_SEVERITY_LABELS = {
    "bloqueante": "BLOQUEANTE",
    "crítica":    "CRÍTICO",
    "mayor":      "MAYOR",
    "menor":      "MENOR",
    "ninguna":    "INFO",
    "feature":    "FEAT",
}


def generate_commit_message(ticket_folder: str, ticket_id: str,
                             project_name: str = "") -> str | None:
    """
    Genera COMMIT_MESSAGE.txt en la carpeta del ticket.
    Retorna la ruta al archivo generado, o None si no se pudo generar.
    """
    output_path = os.path.join(ticket_folder, "COMMIT_MESSAGE.txt")

    # Leer fuentes de información
    inc_content     = _read_safe(ticket_folder, f"INC-{ticket_id}.md",      4000)
    incidente       = _read_safe(ticket_folder, "INCIDENTE.md",              2000)
    dev_completado  = _read_safe(ticket_folder, "DEV_COMPLETADO.md",         3000)
    tester_result   = _read_safe(ticket_folder, "TESTER_COMPLETADO.md",      2000)
    svn_changes     = _read_safe(ticket_folder, "SVN_CHANGES.md",            3000)
    tareas          = _read_safe(ticket_folder, "TAREAS_DESARROLLO.md",      2000)

    if not inc_content and not dev_completado:
        return None

    # ── Extraer datos ─────────────────────────────────────────────────────────
    title       = _extract_title(inc_content)
    severity    = _extract_severity(inc_content or incidente)
    change_type = _infer_change_type(inc_content + " " + incidente + " " + tareas)
    files       = _extract_modified_files(dev_completado, svn_changes)
    qa_verdict  = _extract_verdict(tester_result)
    summary     = _extract_dev_summary(dev_completado)
    proj_tag    = project_name.upper() if project_name else "PROJ"

    # ── Construir mensaje ─────────────────────────────────────────────────────
    lines = []

    # Línea 1: encabezado
    sev_label = _SEVERITY_LABELS.get(severity.lower(), "BUG") if severity else change_type
    lines.append(f"[{proj_tag}][{change_type or sev_label}] #{ticket_id} - {title}")
    lines.append("")

    # Cambios por tarea
    if summary:
        lines.append("Cambios realizados:")
        for s in summary:
            lines.append(f"- {s}")
        lines.append("")

    # Archivos modificados
    if files:
        lines.append(f"Archivos modificados ({len(files)}):")
        for f in files[:10]:
            lines.append(f"  {f}")
        if len(files) > 10:
            lines.append(f"  ... y {len(files) - 10} más")
        lines.append("")

    # Metadata
    metadata = []
    metadata.append(f"Ref: MantisBT #{ticket_id}")
    if qa_verdict:
        metadata.append(f"QA: {qa_verdict}")
    if severity:
        metadata.append(f"Severidad: {severity}")
    metadata.append(f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(" | ".join(metadata))

    # Footer para svn commit -F
    lines.append("")
    lines.append("─" * 60)
    lines.append("Uso: svn commit -F COMMIT_MESSAGE.txt [archivos...]")
    lines.append("O copiar el texto encima de la línea para commit manual")

    message = "\n".join(lines)

    try:
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(message)
        return output_path
    except Exception as e:
        import logging
        logging.getLogger("mantis.commit_gen").error(
            "No se pudo escribir COMMIT_MESSAGE.txt: %s", e
        )
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_safe(folder: str, fname: str, max_chars: int = 3000) -> str:
    path = os.path.join(folder, fname)
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
        return content[:max_chars]
    except Exception:
        return ""


def _extract_title(inc_content: str) -> str:
    """Extrae el título del ticket del INC-xxx.md."""
    for line in inc_content.splitlines():
        stripped = line.strip()
        # Buscar línea de resumen/título
        if stripped.startswith("**Resumen") or stripped.startswith("## Resumen"):
            next_lines = inc_content.split(stripped, 1)[-1].splitlines()
            for nl in next_lines[1:4]:
                nl = nl.strip().lstrip("#").strip()
                if nl and len(nl) > 5:
                    return nl[:100]
        # Primer heading H1 que no sea "Incidencia"
        if stripped.startswith("# ") and "incidencia" not in stripped.lower():
            title = stripped.lstrip("# ").strip()
            if len(title) > 5:
                return title[:100]
    # Fallback: primera línea no vacía
    for line in inc_content.splitlines():
        line = line.strip().lstrip("#- ").strip()
        if len(line) > 10:
            return line[:100]
    return "Sin título"


def _extract_severity(content: str) -> str:
    """Extrae la severidad del ticket."""
    patterns = [
        r'(?:gravedad|severidad|prioridad)[:\s]+\*{0,2}(\w+)',
        r'\*{0,2}(bloqueante|crítica?|mayor|menor|feature|ninguna)\*{0,2}',
    ]
    for pat in patterns:
        m = re.search(pat, content, re.IGNORECASE)
        if m:
            return m.group(1).lower()
    return ""


def _infer_change_type(content: str) -> str:
    """Infiere el tipo de cambio a partir del contenido."""
    content_lower = content.lower()
    scores = {t: 0 for t in _TYPE_KEYWORDS}
    for change_type, keywords in _TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in content_lower:
                scores[change_type] += 1
    best = max(scores, key=lambda t: scores[t])
    return best if scores[best] > 0 else "BUG"


def _extract_modified_files(dev_completado: str, svn_changes: str) -> list[str]:
    """Extrae lista de archivos modificados de DEV_COMPLETADO.md o SVN_CHANGES.md."""
    files = set()
    # Buscar rutas de archivos en ambos documentos
    pat = re.compile(
        r'(?:[\w\-]+[/\\])+[\w\-]+\.(?:cs|aspx|aspx\.cs|vb|sql|config|js)',
        re.IGNORECASE
    )
    for source in [dev_completado, svn_changes]:
        for m in pat.finditer(source):
            path = m.group(0).replace("\\", "/")
            # Filtrar paths del sistema de tickets
            if "mantis_scraper" not in path.lower() and "tools/" not in path.lower():
                files.add(path)
    return sorted(files)[:15]


def _extract_verdict(tester_content: str) -> str:
    """Extrae el veredicto de QA."""
    if not tester_content:
        return ""
    for verdict in ["APROBADO", "CON OBSERVACIONES", "RECHAZADO"]:
        if verdict in tester_content.upper():
            return verdict
    return ""


def _extract_dev_summary(dev_completado: str) -> list[str]:
    """Extrae resumen de cambios de DEV_COMPLETADO.md."""
    summary = []
    in_resumen = False
    for line in dev_completado.splitlines():
        stripped = line.strip()
        if re.match(r'^#+\s*(resumen|cambios|implementación|tareas)', stripped, re.IGNORECASE):
            in_resumen = True
            continue
        if in_resumen and re.match(r'^#+\s', stripped):
            break
        if in_resumen and stripped.startswith(("-", "*", "•")) and len(stripped) > 5:
            summary.append(stripped.lstrip("-*• ").strip())
    return summary[:8]
