"""
rollback_assistant.py — N-10: Rollback Asistido Post-Regresión.

Cuando se detecta una regresión post-commit, genera:
  1. Comandos SVN de revert precisos para los archivos del ticket
  2. Un archivo ROLLBACK.patch con el diff inverso
  3. Instrucciones step-by-step para el desarrollador

No ejecuta el rollback automáticamente — genera el plan y lo pone
a disposición del desarrollador (en ROLLBACK_PLAN.md + notificación).

Uso:
    from rollback_assistant import generate_rollback_plan
    ok = generate_rollback_plan(ticket_id, ticket_folder, workspace_root)
"""

import json
import logging
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("mantis.rollback")


def generate_rollback_plan(ticket_id: str, ticket_folder: str,
                           workspace_root: str,
                           revision: str = "") -> bool:
    """
    Genera ROLLBACK_PLAN.md y ROLLBACK.sh/.bat en la carpeta del ticket.
    revision: revisión SVN del commit a revertir (vacío = usa SVN_CHANGES.md).
    Retorna True si el plan fue generado.
    """
    if not workspace_root or not os.path.isdir(workspace_root):
        logger.warning("[ROLLBACK] workspace_root no válido: %s", workspace_root)
        return False

    # Obtener archivos modificados por este ticket
    files = _get_ticket_files(ticket_folder)
    if not files:
        logger.warning("[ROLLBACK] No se encontraron archivos para rollback del ticket #%s",
                       ticket_id)
        return False

    # Determinar revisión SVN si no se proporcionó
    if not revision:
        revision = _extract_revision(ticket_folder)

    # Generar diff inverso
    patch_content = _generate_inverse_patch(workspace_root, files, revision)

    # Construir plan
    plan = _build_rollback_plan(ticket_id, files, revision, patch_content, workspace_root)

    # Escribir archivos
    plan_path = os.path.join(ticket_folder, "ROLLBACK_PLAN.md")
    try:
        Path(plan_path).write_text(plan, encoding="utf-8")
    except Exception as e:
        logger.error("[ROLLBACK] Error escribiendo ROLLBACK_PLAN.md: %s", e)
        return False

    # Script de rollback (bat + sh)
    _write_rollback_scripts(ticket_folder, ticket_id, files, workspace_root, revision)

    # Metadata JSON
    meta_path = os.path.join(ticket_folder, "ROLLBACK_META.json")
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({
                "ticket_id":    ticket_id,
                "revision":     revision,
                "files":        files,
                "generated_at": datetime.now().isoformat(),
                "workspace":    workspace_root,
            }, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    logger.info("[ROLLBACK] Plan generado para ticket #%s: %d archivos, rev %s",
                ticket_id, len(files), revision or "desconocida")
    return True


# ── Internals ─────────────────────────────────────────────────────────────────

def _get_ticket_files(ticket_folder: str) -> list[str]:
    """Obtiene la lista de archivos modificados por el ticket."""
    files: list[str] = []

    # 1. Desde SVN_CHANGES.md
    svn_path = os.path.join(ticket_folder, "SVN_CHANGES.md")
    if os.path.exists(svn_path):
        content = Path(svn_path).read_text(encoding="utf-8", errors="replace")
        # Buscar líneas de tabla: | M | ruta/archivo.cs |
        for m in re.finditer(r'\|\s*[MADC]\s*\|\s*([\w/\\.]+\.(?:cs|aspx\.cs|aspx|sql|vb))\s*\|',
                             content, re.IGNORECASE):
            f = m.group(1).replace("\\", "/")
            if f not in files:
                files.append(f)

    # 2. Desde DEV_COMPLETADO.md
    dev_path = os.path.join(ticket_folder, "DEV_COMPLETADO.md")
    if os.path.exists(dev_path):
        content = Path(dev_path).read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'[\w/\\]+\.(?:cs|aspx\.cs|aspx|sql|vb)', content, re.IGNORECASE):
            f = m.group(0).replace("\\", "/")
            if f not in files and "mantis" not in f.lower():
                files.append(f)

    # 3. Desde ARQUITECTURA_SOLUCION.md
    arq_path = os.path.join(ticket_folder, "ARQUITECTURA_SOLUCION.md")
    if os.path.exists(arq_path):
        content = Path(arq_path).read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'[\w/\\]+\.(?:cs|aspx\.cs|aspx|sql|vb)', content, re.IGNORECASE):
            f = m.group(0).replace("\\", "/")
            if f not in files and "mantis" not in f.lower():
                files.append(f)

    return files[:20]  # cap en 20 archivos


def _extract_revision(ticket_folder: str) -> str:
    """Intenta extraer la revisión SVN del COMMIT_MESSAGE.txt o SVN_CHANGES.md."""
    commit_path = os.path.join(ticket_folder, "COMMIT_MESSAGE.txt")
    if os.path.exists(commit_path):
        content = Path(commit_path).read_text(encoding="utf-8", errors="replace")
        m = re.search(r'r(?evision)?[:\s]+(\d+)', content, re.IGNORECASE)
        if m:
            return m.group(1)

    svn_path = os.path.join(ticket_folder, "SVN_CHANGES.md")
    if os.path.exists(svn_path):
        content = Path(svn_path).read_text(encoding="utf-8", errors="replace")
        m = re.search(r'[Rr]evisión[:\s]+(\d+)|[Rr]evision[:\s]+(\d+)', content)
        if m:
            return m.group(1) or m.group(2)

    return ""


def _generate_inverse_patch(workspace_root: str, files: list[str],
                             revision: str) -> str:
    """Genera el diff inverso usando svn diff si hay revisión disponible."""
    if not revision:
        return ""
    try:
        prev_rev = str(int(revision) - 1) if revision.isdigit() else ""
        if not prev_rev:
            return ""
        # svn diff -r HEAD:prev para invertir
        cmd = ["svn", "diff", f"-r{revision}:{prev_rev}", "--non-interactive"]
        result = subprocess.run(cmd, capture_output=True, text=True,
                                cwd=workspace_root, timeout=30, encoding="utf-8",
                                errors="replace")
        if result.returncode == 0 and result.stdout:
            return result.stdout[:50000]
    except Exception as e:
        logger.debug("[ROLLBACK] Error generando diff inverso: %s", e)
    return ""


def _build_rollback_plan(ticket_id: str, files: list[str], revision: str,
                         patch_content: str, workspace_root: str) -> str:
    """Construye el contenido de ROLLBACK_PLAN.md."""
    lines = [
        f"# Plan de Rollback — Ticket #{ticket_id}",
        "",
        f"> Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"> Revisión SVN a revertir: `{revision or 'desconocida'}`  ",
        f"> Archivos afectados: {len(files)}",
        "",
        "---",
        "",
        "## ⚠️ Antes de ejecutar el rollback",
        "",
        "1. Verificar que ningún otro ticket dependa de los cambios de este fix",
        "2. Comunicar al equipo que se va a revertir el fix del ticket #{ticket_id}",
        "3. Asegurarse de tener una copia de los archivos actuales (backup manual o SVN)",
        "4. Ejecutar en un workspace limpio (sin cambios pendientes)",
        "",
        "---",
        "",
        "## Archivos a revertir",
        "",
        "| Archivo | Acción |",
        "|---------|--------|",
    ]
    for f in files:
        lines.append(f"| `{f}` | `svn revert` |")

    lines += [
        "",
        "---",
        "",
        "## Comandos SVN",
        "",
        "```bash",
    ]

    if revision:
        lines.append(f"# Opción A: Revertir revisión completa")
        lines.append(f"svn merge -c -{revision} {workspace_root}")
        lines.append(f"svn commit -m \"[ROLLBACK] Reverting r{revision} (Ticket #{ticket_id})\"")
        lines.append("")
        lines.append("# Opción B: Revertir archivos individuales a revisión anterior")
        prev = str(int(revision) - 1) if revision.isdigit() else "PREV"
        for f in files:
            lines.append(f"svn update -r {prev} {f}")
        lines.append(f"svn commit -m \"[ROLLBACK] Reverting files from r{revision} (Ticket #{ticket_id})\"")
    else:
        lines.append("# Revertir cambios locales pendientes")
        for f in files:
            lines.append(f"svn revert {f}")

    lines += [
        "```",
        "",
    ]

    if patch_content:
        lines += [
            "---",
            "",
            "## Diff inverso (patch)",
            "",
            "```diff",
            patch_content[:10000],
            "```",
            "",
        ]

    lines += [
        "---",
        "",
        "## Post-rollback",
        "",
        "- [ ] Verificar que la funcionalidad anterior está restaurada",
        "- [ ] Ejecutar smoke tests en el módulo afectado",
        "- [ ] Notificar al equipo y actualizar el ticket en Mantis",
        "- [ ] Documentar el motivo del rollback en el ticket",
        "",
        "_Plan generado automáticamente por Stacky Rollback Assistant._",
    ]
    return "\n".join(lines)


def _write_rollback_scripts(ticket_folder: str, ticket_id: str,
                             files: list[str], workspace_root: str,
                             revision: str) -> None:
    """Genera rollback.bat (Windows) y rollback.sh (Unix)."""
    ws = workspace_root.replace("/", "\\")

    # Windows .bat
    bat_lines = [
        "@echo off",
        f"echo Rollback Ticket #{ticket_id} — SVN r{revision or '?'}",
        f"cd /d \"{ws}\"",
    ]
    if revision:
        bat_lines.append(f"svn merge -c -{revision} .")
    else:
        for f in files:
            bat_lines.append(f"svn revert \"{f}\"")
    bat_lines += [
        f"svn commit -m \"[ROLLBACK] Reverting Ticket #{ticket_id}\"",
        "echo Rollback completado.",
        "pause",
    ]
    bat_path = os.path.join(ticket_folder, "rollback.bat")
    try:
        Path(bat_path).write_text("\r\n".join(bat_lines), encoding="utf-8")
    except Exception:
        pass

    # Unix .sh
    sh_lines = [
        "#!/bin/bash",
        f"echo 'Rollback Ticket #{ticket_id} — SVN r{revision or \"?\"}'",
        f"cd '{workspace_root}'",
    ]
    if revision:
        sh_lines.append(f"svn merge -c -{revision} .")
    else:
        for f in files:
            sh_lines.append(f"svn revert '{f}'")
    sh_lines += [
        f"svn commit -m '[ROLLBACK] Reverting Ticket #{ticket_id}'",
        "echo 'Rollback completado.'",
    ]
    sh_path = os.path.join(ticket_folder, "rollback.sh")
    try:
        Path(sh_path).write_text("\n".join(sh_lines), encoding="utf-8")
    except Exception:
        pass
