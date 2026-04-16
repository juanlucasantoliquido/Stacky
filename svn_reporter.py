"""
svn_reporter.py — Generación de reporte SVN después de que DEV completa.

Captura qué archivos modificó DEV en el trunk y genera SVN_CHANGES.md en la
carpeta del ticket. Ese archivo se inyecta automáticamente en el prompt de QA
para que sepa exactamente qué revisar, y queda como auditoría permanente.

Uso:
    from svn_reporter import generate_svn_report
    generate_svn_report(workspace_root, ticket_folder)
"""

import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("mantis.svn_reporter")

# Extensiones de código relevantes para el diff
_CODE_EXTENSIONS = {".cs", ".aspx", ".aspx.cs", ".vb", ".sql", ".config",
                    ".js", ".css", ".html", ".xml", ".json"}

# Límite de caracteres del diff completo en el reporte (para no generar un MD gigante)
_MAX_DIFF_CHARS = 30_000


def generate_svn_report(workspace_root: str, ticket_folder: str) -> str | None:
    """
    Ejecuta svn status + svn diff en workspace_root y escribe SVN_CHANGES.md
    en ticket_folder.

    Retorna la ruta al archivo generado, o None si no se pudo generar.
    """
    output_path = os.path.join(ticket_folder, "SVN_CHANGES.md")

    status_output = _run_svn_status(workspace_root)
    if status_output is None:
        logger.warning("[SVN] No se pudo obtener svn status — SVN_CHANGES.md no generado")
        return None

    changed_files = _parse_svn_status(status_output, workspace_root)

    if not changed_files:
        logger.info("[SVN] No hay cambios SVN pendientes en workspace")
        _write_no_changes_report(output_path)
        return output_path

    diff_output = _run_svn_diff(workspace_root, [f["abs_path"] for f in changed_files
                                                   if f["status"] in ("M", "A")])

    _write_report(output_path, changed_files, diff_output, workspace_root)
    logger.info("[SVN] SVN_CHANGES.md generado: %d archivo(s) modificado(s)", len(changed_files))
    return output_path


def get_changed_files(workspace_root: str) -> list[dict]:
    """
    API pública: retorna lista de archivos modificados en el workspace.
    Cada elemento: {abs_path, rel_path, status, status_label}
    """
    status_output = _run_svn_status(workspace_root)
    if status_output is None:
        return []
    return _parse_svn_status(status_output, workspace_root)


# ── Helpers internos ──────────────────────────────────────────────────────────

def _run_svn_status(workspace_root: str) -> str | None:
    """Ejecuta svn status y retorna el output, o None si falla."""
    try:
        result = subprocess.run(
            ["svn", "status", "--non-interactive"],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if result.returncode != 0 and result.stderr:
            logger.debug("[SVN] svn status stderr: %s", result.stderr[:300])
        return result.stdout
    except FileNotFoundError:
        logger.warning("[SVN] svn no encontrado en PATH — instalar Subversion CLI")
        return None
    except subprocess.TimeoutExpired:
        logger.warning("[SVN] svn status timeout")
        return None
    except Exception as e:
        logger.warning("[SVN] Error ejecutando svn status: %s", e)
        return None


def _run_svn_diff(workspace_root: str, file_paths: list[str]) -> str:
    """Ejecuta svn diff sobre los archivos modificados."""
    if not file_paths:
        return ""
    # Filtrar solo extensiones de código relevantes
    code_files = [p for p in file_paths
                  if Path(p).suffix.lower() in _CODE_EXTENSIONS]
    if not code_files:
        return ""
    try:
        result = subprocess.run(
            ["svn", "diff", "--non-interactive"] + code_files,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        return result.stdout
    except Exception as e:
        logger.warning("[SVN] Error ejecutando svn diff: %s", e)
        return ""


_SVN_STATUS_CODES = {
    "M": "Modificado",
    "A": "Agregado",
    "D": "Eliminado",
    "C": "Conflicto",
    "?": "Sin versionar",
    "!": "Faltante",
    "R": "Reemplazado",
}


def _parse_svn_status(output: str, workspace_root: str) -> list[dict]:
    """Parsea el output de svn status y retorna lista de archivos cambiados."""
    changed = []
    ws_path = Path(workspace_root)
    for line in output.splitlines():
        if len(line) < 2:
            continue
        code     = line[0].upper()
        rel_path = line[8:].strip()  # svn status pone 8 cols de flags
        if not rel_path or code not in _SVN_STATUS_CODES:
            continue
        abs_path = str(ws_path / rel_path)
        changed.append({
            "abs_path":     abs_path,
            "rel_path":     rel_path.replace("\\", "/"),
            "status":       code,
            "status_label": _SVN_STATUS_CODES[code],
            "ext":          Path(rel_path).suffix.lower(),
        })
    # Ordenar: código primero, luego por ruta
    return sorted(changed, key=lambda x: (x["status"] != "M", x["rel_path"]))


def _write_report(output_path: str, changed_files: list[dict],
                  diff_output: str, workspace_root: str) -> None:
    """Escribe SVN_CHANGES.md con el reporte completo."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ws_rel = workspace_root.replace("\\", "/")

    lines = [
        f"# SVN Changes — Generado por Stacky",
        f"",
        f"**Timestamp:** {now}  ",
        f"**Workspace:** `{ws_rel}`  ",
        f"**Total archivos modificados:** {len(changed_files)}",
        f"",
        f"---",
        f"",
        f"## Archivos Modificados",
        f"",
        f"| Estado | Archivo | Tipo |",
        f"|--------|---------|------|",
    ]

    for f in changed_files:
        icon = {"M": "✏️", "A": "➕", "D": "🗑️", "C": "⚠️"}.get(f["status"], "•")
        ext  = f["ext"].lstrip(".").upper() or "—"
        lines.append(f"| {icon} {f['status_label']} | `{f['rel_path']}` | {ext} |")

    lines += ["", "---", ""]

    if diff_output:
        # Truncar diff si es muy grande
        diff_to_show = diff_output
        truncated    = False
        if len(diff_output) > _MAX_DIFF_CHARS:
            diff_to_show = diff_output[:_MAX_DIFF_CHARS]
            truncated    = True

        lines += [
            "## Diff de Código",
            "",
            "```diff",
            diff_to_show,
            "```",
        ]
        if truncated:
            lines += [
                "",
                f"> ⚠️ Diff truncado a {_MAX_DIFF_CHARS:,} caracteres. "
                f"Ver diff completo con: `svn diff {ws_rel}`",
            ]
    else:
        lines += [
            "## Diff de Código",
            "",
            "_No hay diff de código disponible (solo archivos no versionados o binarios)._",
        ]

    lines += [
        "",
        "---",
        "",
        "## Instrucción para QA",
        "",
        "Revisá los archivos listados arriba. El diff muestra exactamente qué cambió.",
        "Prestá especial atención a:",
        "",
    ]

    # Destacar archivos de alto impacto
    high_impact = [f for f in changed_files
                   if any(kw in f["rel_path"].lower()
                          for kw in ["dal_", "bll_", "frm", "service", "manager"])]
    if high_impact:
        lines.append("**Archivos de alto impacto (DAL/BLL/Forms):**")
        for f in high_impact:
            lines.append(f"- `{f['rel_path']}`")
    else:
        lines.append("- Todos los archivos listados en la tabla de cambios")

    try:
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
    except Exception as e:
        logger.error("[SVN] No se pudo escribir %s: %s", output_path, e)


def _write_no_changes_report(output_path: str) -> None:
    """Escribe SVN_CHANGES.md indicando que no hay cambios pendientes."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    content = (
        f"# SVN Changes — Generado por Stacky\n\n"
        f"**Timestamp:** {now}\n\n"
        f"> No se detectaron cambios SVN pendientes en el workspace al momento "
        f"de completar DEV.\n\n"
        f"Posibles causas:\n"
        f"- DEV commitó los cambios antes de crear DEV_COMPLETADO.md\n"
        f"- Los cambios fueron realizados en otro workspace\n"
        f"- svn status no detectó modificaciones\n"
    )
    try:
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(content)
    except Exception as e:
        logger.error("[SVN] No se pudo escribir reporte vacío: %s", e)
