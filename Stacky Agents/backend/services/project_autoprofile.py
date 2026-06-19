"""Plan 42 F5 — Auto-perfilado de proyecto desde docs locales.

Algoritmo DETERMINISTA: solo lee archivos reales del árbol de docs, extrae
headings como candidatos a procesos, NUNCA inventa nombres ni propósitos.

Función pública: draft_profile_from_docs(docs_root: Path) -> dict

Gated por STACKY_PROJECT_AUTOPROFILE_ENABLED (default False).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


# Patterns para detectar directorios de doc técnica / funcional.
_TECH_PATTERNS = re.compile(r"^(t[eé]cnica?|technical)$", re.IGNORECASE)
_FUNC_PATTERNS = re.compile(r"^(funcional|functional)$", re.IGNORECASE)
# Headings nivel 2-3 que sugieren un proceso / batch / tarea.
_PROCESS_HEADING = re.compile(
    r"^#{2,3}\s+(.+(?:process|proceso|job|batch|tarea).+)$",
    re.IGNORECASE,
)


def _find_subdir(root: Path, pattern: re.Pattern) -> Path | None:
    """Busca el primer subdirectorio directo que matchee el patrón (case-insensitive)."""
    if not root.is_dir():
        return None
    for child in root.iterdir():
        if child.is_dir() and pattern.match(child.name):
            return child
    return None


def _find_master_index(tech_dir: Path) -> str | None:
    """Busca el primer .md que parezca un índice maestro dentro de tech_dir."""
    if not tech_dir.is_dir():
        return None
    candidates = sorted(tech_dir.glob("*.md"))
    # Preferencia: archivo cuyo nombre contenga INDEX, MASTER o INDICE.
    priority = re.compile(r"(?i)(index|master|indice|maestro)")
    for f in candidates:
        if priority.search(f.name):
            return str(f.relative_to(tech_dir.parent.parent) if tech_dir.parent.parent != tech_dir else f)
    # Fallback: primer .md alphabético.
    return str(candidates[0]) if candidates else None


def _extract_process_candidates(md_file: Path) -> list[dict[str, str]]:
    """Extrae headings nivel 2-3 que describan procesos/batch de un .md.

    NUNCA inventa: solo cita el título exacto del heading como `name` y
    como `purpose`. El operador deberá completar purpose luego.
    Devuelve [] si el archivo no existe o no hay matches.
    """
    if not md_file.is_file():
        return []
    try:
        text = md_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        m = _PROCESS_HEADING.match(line.strip())
        if m:
            name = m.group(1).strip()
            if name and name not in seen:
                seen.add(name)
                results.append({
                    "name": name,
                    "purpose": f"[PENDIENTE: describir propósito de '{name}']",
                    "kind": "batch",
                })
    return results


def draft_profile_from_docs(docs_root: Path) -> dict[str, Any]:
    """Deriva un perfil de proyecto desde los docs locales sin LLM, sin inventar.

    Algoritmo:
    1. Buscar subdirectorio técnico → docs_indexes.technical_master
    2. Buscar subdirectorio funcional → docs_indexes.functional_online
    3. Para cada .md bajo técnica, extraer headings que matcheen proceso/batch
       → process_catalog (solo títulos reales)
    4. NUNCA inventa: solo cita lo que existe en disco.

    Devuelve un dict parcial apto para merge con el perfil base del proyecto.
    """
    profile: dict[str, Any] = {
        "schema_version": 2,
        "docs_indexes": {},
        "process_catalog": [],
        "_autoprofile_source": str(docs_root),
    }

    tech_dir = _find_subdir(docs_root, _TECH_PATTERNS)
    func_dir = _find_subdir(docs_root, _FUNC_PATTERNS)

    if tech_dir is not None:
        master = _find_master_index(tech_dir)
        if master:
            profile["docs_indexes"]["technical_master"] = master

        # Extraer candidatos de procesos de TODOS los .md bajo técnica.
        catalog: list[dict[str, str]] = []
        for md_file in sorted(tech_dir.rglob("*.md")):
            catalog.extend(_extract_process_candidates(md_file))
        profile["process_catalog"] = catalog

    if func_dir is not None:
        # Intentar detectar índice online/batch dentro del directorio funcional.
        online_candidates = [f for f in sorted(func_dir.glob("*.md"))
                             if re.search(r"(?i)(online|on.?line|web)", f.name)]
        batch_candidates = [f for f in sorted(func_dir.glob("*.md"))
                            if re.search(r"(?i)(batch|nocturno|offline)", f.name)]
        if online_candidates:
            profile["docs_indexes"]["functional_online"] = str(online_candidates[0])
        if batch_candidates:
            profile["docs_indexes"]["functional_batch"] = str(batch_candidates[0])
        # Fallback: primer .md alphabético como functional_online.
        if not online_candidates and not batch_candidates:
            all_mds = sorted(func_dir.glob("*.md"))
            if all_mds:
                profile["docs_indexes"]["functional_online"] = str(all_mds[0])

    return profile
