"""F0/F1 (plan 47) — Rescate determinístico del entregable desde el disco.

Causa raíz (epic-brief-ado-not-created): el agente ESCRIBE el HTML de la épica
en `Agentes/outputs/` pero su `output` (last_message) es narración, así que el
backend ve produced_files=[] y degrada a needs_review aunque el artefacto EXISTA.

Este módulo busca en un directorio de outputs el archivo más reciente cuyo
contenido pasa un validador de forma (inyectado: `_looks_like_epic`), y devuelve
su HTML extraído. PURO respecto de red/DB/Flask: solo lee archivos del disco.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

# Extensiones candidatas: el agente escribe HTML o markdown con el bloque ```html.
_CANDIDATE_SUFFIXES = (".html", ".htm", ".md", ".txt")
_MAX_BYTES = 512_000  # 500 KB: una épica nunca es más grande; evita leer binarios enormes.


def find_rescued_html(
    output_dir: Path | str | None,
    *,
    extract: Callable[[str | None], str],
    looks_valid: Callable[[str | None], bool],
    min_mtime: float | None = None,
) -> str | None:
    """Devuelve el HTML del artefacto más reciente y válido bajo output_dir, o None.

    - output_dir None / inexistente → None (caller cae al comportamiento actual).
    - Recorre archivos candidatos por extensión, ORDENADOS por mtime DESC (recursivo:
      el layout real es `Agentes/outputs/epic-<id>/<rf>/...`).
    - min_mtime (C4/R-STALE): si se pasa, se IGNORA todo archivo con mtime <= min_mtime.
      En producción min_mtime = run_started_at (epoch float) → solo se rescata lo que
      el agente escribió DURANTE esta run, nunca una épica vieja del proyecto.
    - Para cada uno: lee texto (utf-8, errors='ignore'), aplica extract() y
      looks_valid(). Devuelve el primero válido (= el más reciente válido).
    - Best-effort: cualquier excepción por archivo se ignora y se sigue.

    `extract` y `looks_valid` se INYECTAN (en producción: api.tickets._extract_epic_html
    y _looks_like_epic) para no acoplar este módulo a api.tickets ni crear import circular.
    """
    if output_dir is None:
        return None
    base = Path(output_dir)
    if not base.exists() or not base.is_dir():
        return None
    candidates: list[tuple[float, int, Path]] = []
    for f in base.rglob("*"):
        if not (f.is_file() and f.suffix.lower() in _CANDIDATE_SUFFIXES):
            continue
        try:
            st = f.stat()
        except Exception:  # noqa: BLE001
            continue
        # C4/R-STALE: descartar artefactos anteriores al inicio de la run.
        if min_mtime is not None and st.st_mtime <= min_mtime:
            continue
        candidates.append((st.st_mtime, st.st_size, f))
    # Más reciente primero: el último entregable escrito gana.
    candidates.sort(key=lambda t: t[0], reverse=True)
    for _mtime, size, f in candidates:
        try:
            if size > _MAX_BYTES:
                continue
            raw = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            continue
        html = extract(raw)
        if looks_valid(html):
            return html
    return None


def resolve_outputs_dir() -> Path | None:
    """Devuelve <repo_root>/Agentes/outputs si existe, o None.

    Reusa runtime_paths.repo_root() (override STACKY_REPO_ROOT > workspace del
    proyecto activo > layout de fuentes; frozen-safe). NO inventa rutas: la
    convención `Agentes/outputs` es la misma que documenta runtime_paths.repo_root.

    OJO (C3): repo_root() tiene firma `-> Path` y NUNCA devuelve None: en deploy
    congelado sin proyecto activo devuelve un *sentinel inexistente*
    (`_UNRESOLVED_REPO_ROOT`, runtime_paths.py:135). Por eso la única validación
    válida acá es `out.exists() and out.is_dir()` — NO `if root is None`.
    """
    try:
        from runtime_paths import repo_root  # lazy: evita import en contextos sin proyecto
        root = repo_root()
    except Exception:  # noqa: BLE001
        return None
    out = Path(root) / "Agentes" / "outputs"
    return out if out.exists() and out.is_dir() else None
