"""Plan 131 — Resolutor de incidencias multimodal: intake (store de persistencia).

Contrato §4.1 del plan: límites/almacenamiento del intake (texto + archivos) que
el operador carga en el modal "Resolver incidencia". Constantes LITERALES.
"""
from __future__ import annotations

MAX_FILES = 10
MAX_FILE_BYTES = 10 * 1024 * 1024        # 10 MB por archivo
MAX_TOTAL_BYTES = 25 * 1024 * 1024       # 25 MB por incidencia
MAX_TEXT_LEN = 20_000                    # caracteres del texto libre
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
TEXT_EXTENSIONS = {".txt", ".log", ".md", ".json", ".csv", ".xml", ".yaml", ".yml",
                   ".sql", ".ps1", ".sh", ".py", ".cs", ".ts", ".tsx", ".js",
                   ".html", ".css", ".config"}
ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | TEXT_EXTENSIONS | {".pdf"}
