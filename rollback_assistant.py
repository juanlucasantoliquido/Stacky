"""
rollback_assistant.py — N-10: Rollback Asistido Post-Regresión.

Cuando se detecta una regresión post-commit, genera:
  1. Comandos git revert precisos para el commit del ticket
  2. Instrucciones step-by-step para el desarrollador

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

logger = logging.getLogger("stacky.rollback")


def generate_rollback_plan(ticket_id: str, ticket_folder: str,
                           workspace_root: str,
                           revision: str = "") -> bool:
    """
    Genera ROLLBACK_PLAN.md en la carpeta del ticket.
    revision: commit hash de git a revertir (vacío = busca en GIT_CHANGES.md).
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

    # Determinar commit hash si no se proporcionó
    if not revision:
        revision = _extract_revision(ticket_folder)

    # Construir plan
    plan = _build_rollback_plan(ticket_id, files, revision, workspace_root)

    # Escribir archivos
    plan_path = os.path.join(ticket_folder, "ROLLBACK_PLAN.md")
    try:
        Path(plan_path).write_text(plan, encoding="utf-8")
    except Exception as e:
        logger.error("[ROLLBACK] Error escribiendo ROLLBACK_PLAN.md: %s", e)
        return False

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

    logger.info("[ROLLBACK] Plan generado para ticket #%s: %d archivos, commit %s",
                ticket_id, len(files), revision or "desconocido")
    return True


# ── Internals ─────────────────────────────────────────────────────────────────

def _get_ticket_files(ticket_folder: str) -> list[str]:
    """Obtiene la lista de archivos modificados por el ticket."""
    files: list[str] = []

    # 1. Desde GIT_CHANGES.md
    git_path = os.path.join(ticket_folder, "GIT_CHANGES.md")
    if os.path.exists(git_path):
        content = Path(git_path).read_text(encoding="utf-8", errors="replace")
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
            if f not in files and "stacky" not in f.lower():
                files.append(f)

    # 3. Desde ARQUITECTURA_SOLUCION.md
    arq_path = os.path.join(ticket_folder, "ARQUITECTURA_SOLUCION.md")
    if os.path.exists(arq_path):
        content = Path(arq_path).read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'[\w/\\]+\.(?:cs|aspx\.cs|aspx|sql|vb)', content, re.IGNORECASE):
            f = m.group(0).replace("\\", "/")
            if f not in files and "stacky" not in f.lower():
                files.append(f)

    return files[:20]


def _extract_revision(ticket_folder: str) -> str:
    """Intenta extraer el commit hash del COMMIT_MESSAGE.txt o GIT_CHANGES.md."""
    commit_path = os.path.join(ticket_folder, "COMMIT_MESSAGE.txt")
    if os.path.exists(commit_path):
        content = Path(commit_path).read_text(encoding="utf-8", errors="replace")
        m = re.search(r'[Cc]ommit[:\s]+([0-9a-f]{7,40})', content)
        if m:
            return m.group(1)

    git_path = os.path.join(ticket_folder, "GIT_CHANGES.md")
    if os.path.exists(git_path):
        content = Path(git_path).read_text(encoding="utf-8", errors="replace")
        m = re.search(r'[Cc]ommit[:\s]+([0-9a-f]{7,40})', content)
        if m:
            return m.group(1)

    return ""


def _build_rollback_plan(ticket_id: str, files: list[str], revision: str,
                         workspace_root: str) -> str:
    """Construye el contenido de ROLLBACK_PLAN.md."""
    lines = [
        f"# Plan de Rollback — Ticket #{ticket_id}",
        "",
        f"> Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"> Commit a revertir: `{revision or 'desconocido'}`  ",
        f"> Archivos afectados: {len(files)}",
        "",
        "---",
        "",
        "## Antes de ejecutar el rollback",
        "",
        "1. Verificar que ningún otro ticket dependa de los cambios de este fix",
        "2. Comunicar al equipo que se va a revertir el fix del ticket",
        "3. Asegurarse de tener un workspace limpio (sin cambios pendientes)",
        "",
        "---",
        "",
        "## Archivos afectados",
        "",
        "| Archivo | Acción |",
        "|---------|--------|",
    ]
    for f in files:
        lines.append(f"| `{f}` | `git revert` |")

    lines += [
        "",
        "---",
        "",
        "## Comandos Git",
        "",
        "```bash",
    ]

    if revision:
        lines.append(f"# Revertir el commit completo")
        lines.append(f"git revert {revision}")
        lines.append(f"# O si necesitás revertir sin commit automático:")
        lines.append(f"git revert --no-commit {revision}")
        lines.append(f"git commit -m \"[ROLLBACK] Reverting {revision[:8]} (Ticket #{ticket_id})\"")
    else:
        lines.append("# Restaurar archivos individuales al estado anterior")
        for f in files:
            lines.append(f"git checkout HEAD~1 -- {f}")
        lines.append(f"git commit -m \"[ROLLBACK] Reverting Ticket #{ticket_id}\"")

    lines += [
        "```",
        "",
        "---",
        "",
        "## Post-rollback",
        "",
        "- [ ] Verificar que la funcionalidad anterior está restaurada",
        "- [ ] Ejecutar smoke tests en el módulo afectado",
        "- [ ] Notificar al equipo y actualizar el work item en Azure DevOps",
        "- [ ] Documentar el motivo del rollback en el ticket",
        "- [ ] `git push` para publicar el revert",
        "",
        "_Plan generado automáticamente por Stacky Rollback Assistant._",
    ]
    return "\n".join(lines)
