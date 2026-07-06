"""pipeline_stack_detector.py — Plan 97 F2.
Detector determinista de stack técnico por archivos de manifiesto.
PURO respecto del resultado (misma entrada -> misma salida); el único I/O es
lectura de disco (os.path.exists), sin parseo de contenido, sin red, sin LLM.
"""
from __future__ import annotations
import os

# Orden de precedencia: si hay señales de más de un stack (monorepo), gana el
# primero de esta lista (Python > Node > .NET) — decisión arbitraria pero
# DETERMINISTA y documentada; el operador siempre puede elegir manualmente.
_MANIFEST_SIGNALS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("python", ("requirements.txt", "pyproject.toml", "Pipfile")),
    ("node", ("package.json",)),
    ("dotnet", (".csproj", ".sln")),  # sufijos: se busca CUALQUIER archivo que TERMINE así
)


def detect_stack(project_root: str) -> str | None:
    """Devuelve 'python' | 'node' | 'dotnet' | None (sin señal clara o ruta inválida).
    NUNCA lanza: cualquier error de filesystem (permiso denegado, ruta
    inexistente) se traduce a None. Busca en el nivel raíz Y en subcarpetas de
    profundidad máxima 2 (para monorepos simples tipo backend/ + frontend/),
    con un tope de 500 entradas escaneadas para no colgar en árboles gigantes."""
    if not project_root or not os.path.isdir(project_root):
        return None
    project_root = os.path.normpath(project_root)  # C4: normaliza separador final (evita off-by-one de profundidad)
    try:
        scanned = 0
        found: set[str] = set()
        for dirpath, dirnames, filenames in os.walk(project_root):
            depth = dirpath[len(project_root):].count(os.sep)
            if depth >= 2:
                dirnames[:] = []  # no bajar más
            # ignorar carpetas pesadas conocidas (mismo criterio que .gitignore típico)
            dirnames[:] = [d for d in dirnames if d not in
                           ("node_modules", ".git", "venv", ".venv", "bin", "obj", "__pycache__")]
            for fname in filenames:
                scanned += 1
                if scanned > 500:
                    break
                for stack_id, patterns in _MANIFEST_SIGNALS:
                    for pat in patterns:
                        if pat.startswith(".") and fname.endswith(pat):
                            found.add(stack_id)
                        elif fname == pat:
                            found.add(stack_id)
            if scanned > 500:
                break
        for stack_id, _ in _MANIFEST_SIGNALS:
            if stack_id in found:
                return stack_id
        return None
    except OSError:
        return None
