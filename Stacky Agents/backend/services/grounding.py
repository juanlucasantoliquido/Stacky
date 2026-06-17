"""G1.2 — Grounding determinista de referencias del output (rutas/IDs).

check_references(output_text, repo_root, ado_resolver) -> GroundingResult

Extrae rutas de archivo en contexto de lectura/modificación (NUNCA las de
creación propuesta) y work-item IDs/parent-ids; verifica existencia.
Produce metadata["grounding"] = {unresolved_paths: [...], unresolved_ids: [...]}.

Solo corre si STACKY_OUTPUT_GROUNDING_ENABLED=true.
Con flag OFF: devuelve resultado vacío (byte-idéntico en finalize_run).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("stacky.services.grounding")

# Patrones de rutas en contexto de lectura/modificación (no creación).
# Se excluyen deliberadamente patrones de creación ("crear", "crea", "nuevo archivo").
_READ_PATTERNS: list[re.Pattern] = [
    re.compile(r'(?:modificar?|editar?|actualizar?|cambiar?|revisar?|ver|leer?)\s+[`\'"]([^`\'"]+)[`\'"]', re.IGNORECASE),
    re.compile(r'(?:en el archivo|en el módulo|en el fichero)\s+[`\'"]([^`\'"]+)[`\'"]', re.IGNORECASE),
    re.compile(r'(?:archivo|módulo|fichero)\s+[`\'"]([^`\'"]+)[`\'"].*(?:existe|contiene|tiene)', re.IGNORECASE),
    re.compile(r'[`\'"]([a-zA-Z0-9_./-]+\.[a-zA-Z]{1,6})[`\'"]', re.IGNORECASE),
]

# Patrones de creación → excluir estas rutas del grounding.
_CREATE_PATTERNS: list[re.Pattern] = [
    re.compile(r'(?:crear?|crea[r]?|nuevo|generar?|agregar?)\s+(?:el archivo\s+|el fichero\s+|un archivo\s+)?[`\'"]([^`\'"]+)[`\'"]', re.IGNORECASE),
    re.compile(r'[`\'"]([^`\'"]+)[`\'"].*(?:se creará|será creado|se generará|nuevo archivo)', re.IGNORECASE),
]

# Patrones de work-item IDs (ADO).
_ID_PATTERNS: list[re.Pattern] = [
    re.compile(r'\b(?:work.?item|task|ticket|ADO|parent[- ]id|parent_id)[#\s:]+(\d{3,9})\b', re.IGNORECASE),
    re.compile(r'#(\d{4,9})\b'),
]

# Extensiones que ignoramos (no son archivos de proyecto verificables).
_IGNORE_EXTS = {".md", ".txt", ".log", ".env", ".json", ".yaml", ".yml", ".toml"}


@dataclass
class GroundingResult:
    unresolved_paths: list[str] = field(default_factory=list)
    unresolved_ids: list[str] = field(default_factory=list)
    checked_paths: int = 0
    checked_ids: int = 0

    @property
    def clean(self) -> bool:
        return not self.unresolved_paths and not self.unresolved_ids

    def to_metadata(self) -> dict[str, Any]:
        return {
            "grounding": {
                "unresolved_paths": list(self.unresolved_paths),
                "unresolved_ids": list(self.unresolved_ids),
                "checked_paths": self.checked_paths,
                "checked_ids": self.checked_ids,
            }
        }


def check_references(
    output_text: str,
    repo_root: Path | str | None = None,
    ado_resolver: Callable[[str], bool] | None = None,
) -> GroundingResult:
    """Extrae y verifica referencias del output del agente.

    Args:
        output_text: texto de salida del run.
        repo_root: raíz del repositorio para verificar rutas de archivo.
                   None → se intenta resolver desde config; sin repo = skip paths.
        ado_resolver: callable(id_str) -> bool que devuelve True si el ID existe
                      en ADO. None → se intenta usar ado_read_cache; sin resolver = skip.

    Returns:
        GroundingResult con las listas de referencias no ancladas.
    """
    try:
        from config import config as _cfg
        enabled = _cfg.STACKY_OUTPUT_GROUNDING_ENABLED
    except Exception:  # noqa: BLE001
        import os
        enabled = os.getenv("STACKY_OUTPUT_GROUNDING_ENABLED", "false").lower() in (
            "1", "true", "yes"
        )

    if not enabled:
        return GroundingResult()

    result = GroundingResult()

    # ── Rutas de archivo ──────────────────────────────────────────────────────
    root = _resolve_repo_root(repo_root)
    if root is not None:
        create_paths = _extract_create_paths(output_text)
        read_paths = _extract_read_paths(output_text)
        # Excluir explícitamente las rutas de creación.
        paths_to_check = read_paths - create_paths
        for raw_path in sorted(paths_to_check):
            candidate = _try_resolve_path(raw_path, root)
            if candidate is None:
                continue  # no parece una ruta de proyecto
            result.checked_paths += 1
            if not candidate.exists():
                result.unresolved_paths.append(raw_path)

    # ── Work-item IDs / parent-ids ────────────────────────────────────────────
    ids = _extract_ado_ids(output_text)
    if ids:
        resolver = ado_resolver or _build_default_resolver()
        for id_str in sorted(ids):
            result.checked_ids += 1
            try:
                exists = resolver(id_str)
            except Exception:  # noqa: BLE001
                continue  # fallo transitorio → no marcar como no anclado
            if not exists:
                result.unresolved_ids.append(id_str)

    return result


# ── Helpers privados ──────────────────────────────────────────────────────────


def _extract_create_paths(text: str) -> set[str]:
    """Extrae rutas que el output propone CREAR (excluirlas del grounding)."""
    found: set[str] = set()
    for pat in _CREATE_PATTERNS:
        for m in pat.finditer(text):
            found.add(m.group(1).strip())
    return found


def _extract_read_paths(text: str) -> set[str]:
    """Extrae rutas referenciadas en contexto de lectura/modificación."""
    found: set[str] = set()
    for pat in _READ_PATTERNS:
        for m in pat.finditer(text):
            raw = m.group(1).strip()
            if _looks_like_file_path(raw):
                found.add(raw)
    return found


def _looks_like_file_path(s: str) -> bool:
    """Heurística: descarta cadenas que no parecen rutas de archivo."""
    if not s or len(s) < 4:
        return False
    # Debe tener extensión o separador de ruta.
    has_ext = "." in s.rsplit("/", 1)[-1]
    has_sep = "/" in s or "\\" in s
    return has_ext or has_sep


def _try_resolve_path(raw: str, root: Path) -> Path | None:
    """Intenta resolver una ruta relativa al repo_root.

    Devuelve None si la ruta no parece ser de proyecto (e.g. URL, ruta de sistema).
    """
    raw = raw.strip().lstrip("/\\")
    # Ignorar URLs y rutas absolutas de sistema que no son del repo.
    if raw.startswith(("http://", "https://", "ftp://", "C:", "D:", "E:")):
        return None
    # Ignorar extensiones de documentación/config puras.
    p = Path(raw)
    if p.suffix.lower() in _IGNORE_EXTS and "/" not in raw and "\\" not in raw:
        return None
    candidate = root / p
    return candidate


def _extract_ado_ids(text: str) -> set[str]:
    """Extrae IDs de work-items ADO del texto."""
    found: set[str] = set()
    for pat in _ID_PATTERNS:
        for m in pat.finditer(text):
            id_str = m.group(1).strip()
            # Filtrar IDs demasiado cortos (evitar falsos positivos con años, etc.)
            if len(id_str) >= 4:
                found.add(id_str)
    return found


def _resolve_repo_root(repo_root: Path | str | None) -> Path | None:
    """Resuelve el repo_root desde parámetro o config."""
    if repo_root is not None:
        p = Path(repo_root)
        return p if p.exists() else None
    # Intentar obtener del proyecto activo.
    try:
        from project_manager import get_active_project, get_project_config
        active = get_active_project()
        if active:
            cfg = get_project_config(active) or {}
            raw = cfg.get("repo_path") or cfg.get("repo") or ""
            if raw:
                p2 = Path(raw).expanduser()
                if p2.exists():
                    return p2
    except Exception:  # noqa: BLE001
        pass
    return None


def _build_default_resolver() -> Callable[[str], bool] | None:
    """Construye un resolver de IDs ADO usando ado_read_cache si está disponible."""
    try:
        from services.ado_read_cache import _singleton as _cache
        from config import config as _cfg
        ttl = _cfg.STACKY_ADO_READ_CACHE_TTL_SEC

        def _resolve_via_cache(id_str: str) -> bool:
            """Verifica existencia de un work-item via ado_read_cache."""
            key = ("grounding", id_str, "exists")
            def _fetch() -> bool:
                return _ado_check_exists(id_str)
            try:
                return bool(_cache.get_or_fetch(key, _fetch, ttl))
            except Exception:  # noqa: BLE001
                return _ado_check_exists(id_str)

        return _resolve_via_cache
    except Exception:  # noqa: BLE001
        pass
    # Fallback directo sin caché.
    return _ado_check_exists


def _ado_check_exists(id_str: str) -> bool:
    """Verifica existencia de un work-item ADO con una llamada mínima."""
    try:
        import os
        import requests
        org = os.getenv("ADO_ORG", "")
        project = os.getenv("ADO_PROJECT", "")
        pat = os.getenv("ADO_PAT", "")
        if not (org and project and pat):
            return True  # sin credenciales: no marcar como no anclado
        url = (
            f"https://dev.azure.com/{org}/{project}/_apis/wit/workitems/{id_str}"
            "?$select=id&api-version=7.0"
        )
        resp = requests.get(url, auth=("", pat), timeout=10)
        return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return True  # error transitorio → no marcar como no anclado
