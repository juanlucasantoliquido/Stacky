"""
svn_ops.py — Operaciones SVN para Stacky.

Funciones:
  - diff_summarize(path)         → lista de archivos modificados con status (M/A/D)
  - diff_full(path)              → diff completo en texto
  - svn_info(path)               → info del repo (URL, revision actual)
  - export_prev_revision(files)  → exporta la revision anterior de archivos dados
  - commit(path, message)        → hace svn commit con el mensaje dado
  - get_revision(path)           → revision actual del working copy
"""

import os
import re
import subprocess
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.svn")

# Timeout en segundos para operaciones SVN
_TIMEOUT = 60

# Rutas donde TortoiseSVN / SlikSVN / CollabNet instalan svn.exe
_SVN_SEARCH_PATHS = [
    r"C:\Program Files\TortoiseSVN\bin\svn.exe",
    r"C:\Program Files (x86)\TortoiseSVN\bin\svn.exe",
    r"C:\Program Files\SlikSvn\bin\svn.exe",
    r"C:\Program Files (x86)\SlikSvn\bin\svn.exe",
    r"C:\Program Files\CollabNet\Subversion Client\svn.exe",
    r"C:\Program Files (x86)\CollabNet\Subversion Client\svn.exe",
    r"C:\Program Files\VisualSVN\bin\svn.exe",
    r"C:\Program Files (x86)\VisualSVN\bin\svn.exe",
    r"C:\TortoiseSVN\bin\svn.exe",
    r"C:\SVN\bin\svn.exe",
    r"C:\tools\svn\bin\svn.exe",
]

_svn_exe: Optional[str] = None  # caché para no buscar en cada llamada


def _find_svn() -> str:
    """
    Retorna la ruta al ejecutable svn.
    Primero busca en PATH, luego en rutas típicas de TortoiseSVN/SlikSVN.
    Lanza FileNotFoundError si no encuentra nada.
    """
    global _svn_exe
    if _svn_exe:
        return _svn_exe

    # 1. Buscar en PATH (caso normal cuando está configurado)
    import shutil
    found = shutil.which("svn")
    if found:
        _svn_exe = found
        return _svn_exe

    # 2. Buscar en rutas conocidas
    for candidate in _SVN_SEARCH_PATHS:
        if Path(candidate).is_file():
            _svn_exe = candidate
            logger.info("svn encontrado en: %s", _svn_exe)
            return _svn_exe

    # 3. Buscar en subdirectorios de Program Files dinámicamente
    for base in [r"C:\Program Files", r"C:\Program Files (x86)"]:
        base_path = Path(base)
        if not base_path.exists():
            continue
        for svn_exe in base_path.rglob("svn.exe"):
            _svn_exe = str(svn_exe)
            logger.info("svn encontrado en: %s", _svn_exe)
            return _svn_exe

    raise FileNotFoundError(
        "No se encontró svn.exe. Opciones:\n"
        "  1) TortoiseSVN: al instalar, tildar 'command line client tools'\n"
        "     Descarga: https://tortoisesvn.net/downloads.html\n"
        "  2) SlikSVN (standalone): https://sliksvn.com/download/\n"
        "  3) Si ya tenés alguno instalado, agregá la carpeta bin\\ al PATH de Windows.\n"
        "  Rutas buscadas: PATH del sistema + "
        + ", ".join(_SVN_SEARCH_PATHS[:4]) + ", ..."
    )


def _run(args: list, cwd: str = None, timeout: int = _TIMEOUT) -> subprocess.CompletedProcess:
    # Reemplazar "svn" por la ruta completa si es el primer argumento
    if args and args[0] == "svn":
        args = [_find_svn()] + args[1:]
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
    )


# ── Diff summarize ────────────────────────────────────────────────────────────

def diff_summarize(workspace: str) -> list[dict]:
    """
    Ejecuta `svn diff --summarize` y retorna lista de dicts:
      { path, status }  donde status es 'M', 'A', 'D' o '?'

    Esta es la fuente de verdad para saber qué archivos realmente cambiaron
    desde el último commit — independientemente de lo que diga DEV_COMPLETADO.md.
    """
    try:
        r = _run(["svn", "diff", "--summarize", workspace])
        results = []
        for line in r.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            # Formato: "M       path/to/file.cs"
            status = line[0] if line else "?"
            path   = line[8:].strip() if len(line) > 8 else line[1:].strip()
            if path:
                results.append({"path": path.replace("\\", "/"), "status": status})
        return results
    except Exception as e:
        logger.warning("svn diff --summarize falló: %s", e)
        return []


def status(workspace: str) -> list[dict]:
    """
    Ejecuta `svn status` y retorna archivos con cambios locales (incluyendo no versionados).
    """
    try:
        r = _run(["svn", "status", workspace])
        results = []
        for line in r.stdout.splitlines():
            if not line.strip():
                continue
            status_char = line[0]
            path = line[8:].strip() if len(line) > 8 else line[1:].strip()
            if path and status_char in "MADC?!":
                results.append({"path": path.replace("\\", "/"), "status": status_char})
        return results
    except Exception as e:
        logger.warning("svn status falló: %s", e)
        return []


# ── Diff full ─────────────────────────────────────────────────────────────────

def diff_full(workspace: str, files: list[str] = None) -> str:
    """
    Retorna el diff unificado completo del workspace (o de los archivos dados).
    """
    try:
        args = ["svn", "diff"]
        if files:
            args += files
        else:
            args.append(workspace)
        r = _run(args, timeout=120)
        return r.stdout
    except Exception as e:
        logger.warning("svn diff falló: %s", e)
        return ""


# ── SVN Info ──────────────────────────────────────────────────────────────────

def svn_info(path: str) -> dict:
    """
    Retorna dict con: url, revision, root, last_changed_rev, last_changed_author.
    """
    try:
        r = _run(["svn", "info", path])
        info = {}
        for line in r.stdout.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                info[k.strip()] = v.strip()
        return {
            "url":                 info.get("URL", ""),
            "root":                info.get("Repository Root", ""),
            "revision":            info.get("Revision", ""),
            "last_changed_rev":    info.get("Last Changed Rev", ""),
            "last_changed_author": info.get("Last Changed Author", ""),
            "last_changed_date":   info.get("Last Changed Date", ""),
        }
    except Exception as e:
        logger.warning("svn info falló: %s", e)
        return {}


def get_revision(path: str) -> Optional[str]:
    info = svn_info(path)
    return info.get("revision") or None


# ── Export revision anterior ──────────────────────────────────────────────────

def export_prev_revision(file_paths: list[str], dest_dir: str) -> list[dict]:
    """
    Para cada archivo, exporta la revisión anterior (BASE o PREV) a dest_dir.
    Retorna lista de dicts: { original, exported, ok, error }.

    Útil para generar el paquete de rollback — los binarios "viejos" antes del cambio.
    """
    results = []
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    for fpath in file_paths:
        p = Path(fpath)
        out_name = p.name
        out_path = dest / out_name

        # Intentar con svn export -r BASE (última versión commiteada)
        try:
            r = _run(["svn", "export", "--force", "-r", "BASE", fpath, str(out_path)])
            if r.returncode == 0 and out_path.exists():
                results.append({"original": fpath, "exported": str(out_path), "ok": True})
                continue
        except Exception as e:
            pass

        # Fallback: PREV (la revisión anterior a la actual)
        try:
            r = _run(["svn", "export", "--force", "-r", "PREV", fpath, str(out_path)])
            if r.returncode == 0 and out_path.exists():
                results.append({"original": fpath, "exported": str(out_path),
                                 "ok": True, "rev": "PREV"})
                continue
        except Exception as e:
            pass

        results.append({
            "original": fpath,
            "exported": None,
            "ok":       False,
            "error":    f"No se pudo exportar: {r.stderr[:200] if 'r' in dir() else 'error desconocido'}",
        })

    return results


# ── SVN Commit ───────────────────────────────────────────────────────────────

def commit(workspace: str, message: str, files: list[str] = None) -> dict:
    """
    Realiza `svn commit` con el mensaje dado.
    Si `files` es None, commitea todos los cambios en workspace.
    Retorna { ok, revision, output, error }.
    """
    # Asegurar mensaje de una sola línea para evitar problemas con el shell en Windows
    message = " ".join(message.splitlines()).strip()
    args = ["svn", "commit", "-m", message]
    if files:
        args += files
    else:
        args.append(workspace)

    try:
        r = _run(args, timeout=120)
        # Extraer número de revisión del output: "Committed revision 12345."
        rev_match = re.search(r"Committed revision (\d+)", r.stdout)
        revision  = rev_match.group(1) if rev_match else None

        if r.returncode == 0:
            return {"ok": True, "revision": revision, "output": r.stdout}
        else:
            return {
                "ok":     False,
                "error":  r.stderr or r.stdout,
                "output": r.stdout,
            }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Timeout esperando svn commit"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Proposed commit message ───────────────────────────────────────────────────

def build_commit_message(ticket_id: str, ticket_folder: str) -> str:
    """
    Construye un mensaje de commit propuesto siguiendo el formato:
      #<ticket_id> <resumen en 1-2 líneas>

    El resumen se extrae de INCIDENTE.md o del título del ticket.
    El #ticket_id al inicio hace que Mantis lo linkee automáticamente.
    """
    folder = Path(ticket_folder)

    # Limpiar ticket_id: quitar ceros a la izquierda para el link Mantis
    clean_id = str(int(ticket_id)) if ticket_id.isdigit() else ticket_id

    summary = _extract_summary(folder, ticket_id)
    # Garantizar mensaje de una sola línea (SVN acepta -m con newlines pero es confuso)
    msg = f"#{clean_id} {summary}"
    msg = " ".join(msg.splitlines())  # colapsar cualquier salto de línea
    return msg.strip()


def _extract_summary(folder: Path, ticket_id: str) -> str:
    """Extrae el resumen del ticket desde los archivos de análisis."""

    # 1. INCIDENTE.md — primera sección suele tener el resumen ejecutivo
    inc_md = folder / "INCIDENTE.md"
    if inc_md.exists():
        text = inc_md.read_text(encoding="utf-8", errors="ignore")
        summary = _first_meaningful_line(text, max_len=120)
        if summary:
            return summary

    # 2. DEV_COMPLETADO.md — qué implementó el dev (más técnico)
    dev_md = folder / "DEV_COMPLETADO.md"
    if dev_md.exists():
        text = dev_md.read_text(encoding="utf-8", errors="ignore")
        summary = _first_meaningful_line(text, max_len=120)
        if summary:
            return summary

    # 3. Título del INC
    inc_raw = folder / f"INC-{ticket_id}.md"
    if inc_raw.exists():
        text = inc_raw.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("**Título:**"):
                title = line.replace("**Título:**", "").strip()
                # Quitar el prefijo [I12345] si está
                title = re.sub(r"^\[I?\d+\]\s*", "", title)
                return title[:120]
            if line.startswith("# "):
                return line.lstrip("# ").strip()[:120]

    return f"Corrección ticket #{ticket_id}"


def _first_meaningful_line(text: str, max_len: int = 120) -> str:
    """Primera línea de texto con al menos 20 chars, sin ser encabezado markdown."""
    for line in text.splitlines():
        line = line.strip()
        # Saltar encabezados markdown, líneas vacías, separadores, tablas y HTML
        if not line:
            continue
        if line.startswith(("#", "---", "**", "|", "!", "<", ">")):
            continue
        if len(line) >= 20:
            return line[:max_len]
    return ""
