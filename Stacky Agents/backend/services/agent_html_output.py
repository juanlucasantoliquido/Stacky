"""
agent_html_output.py — Lee y valida el output HTML que los agentes generan
para que Stacky lo publique en Azure DevOps.

Contrato de path:
    <repo_root>/Agentes/outputs/<ADO_ID>/comment.html
    <repo_root>/Agentes/outputs/<ADO_ID>/comment.meta.json   (opcional)

Si el agente PATCHea su stacky-status incluyendo `html_output_path`, ese path
gana sobre la convención. Aceptamos paths relativos al root del repo o
absolutos; cualquier intento de salir del directorio `Agentes/outputs/` es
rechazado por `validate_path()`.

REGLA CRÍTICA (Fase 3, plan PLAN-stacky-agents-state-sync-ado-delegation.md):
Este módulo NO publica en ADO; solo LEE y VALIDA. La publicación es
responsabilidad exclusiva de `services.ado_publisher`. Los agentes NUNCA
deben tocar ADO directamente.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.agent_html_output")


# ── Configuración ─────────────────────────────────────────────────────────────

# Tamaño máximo del HTML del agente (bytes). Comentarios ADO razonables.
MAX_HTML_BYTES = 256 * 1024  # 256 KB

# Sub-path obligatorio bajo el cual debe vivir cualquier HTML del agente.
# Cualquier path resuelto fuera de este subárbol es rechazado por seguridad.
OUTPUTS_SUBDIR = ("Agentes", "outputs")

# Patrones heurísticos de posibles secretos en el HTML.
# No pretende ser exhaustivo — es un guardrail de último recurso.
_SECRET_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"ghp_[A-Za-z0-9]{30,}", re.IGNORECASE),       # GitHub PAT
    re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}", re.IGNORECASE),  # Slack
    re.compile(r"AIza[0-9A-Za-z\-_]{30,}"),                   # Google API
    re.compile(r"AKIA[0-9A-Z]{16}"),                          # AWS access key
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),        # private key
    # PAT de Azure DevOps (Basic auth header) — guardrail explícito
    re.compile(r"Authorization:\s*Basic\s+[A-Za-z0-9+/=]{20,}", re.IGNORECASE),
    # PAT name explícito en el HTML (señal clara de leak)
    re.compile(r"\bADO_PAT\s*[=:]\s*\S+", re.IGNORECASE),
)


# ── Resultado tipado ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class HtmlOutput:
    """Resultado de localizar+validar el HTML del agente."""

    path: Path
    html: str
    size_bytes: int
    meta: dict | None  # contenido de comment.meta.json si existe
    ado_id: int


class ValidationError(Exception):
    """Razón estructurada por la que un HTML fue rechazado.

    Códigos posibles:
      NOT_FOUND, TOO_LARGE, EMPTY, SECRET_DETECTED, PATH_ESCAPE, INVALID_PATH
    """

    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


# ── API pública ───────────────────────────────────────────────────────────────


def repo_root() -> Path:
    """Root del repo donde viven `Agentes/outputs`.

    Delega en `runtime_paths.repo_root()`, que es frozen-aware (honra
    `STACKY_REPO_ROOT`, luego el `workspace_root` del proyecto activo en deploy
    congelado, luego el layout de fuentes). Antes resolvía con `parents[5]`
    desde este módulo, lo que en el .exe de PyInstaller aterrizaba fuera del
    repo del cliente y dejaba al output_watcher mirando un directorio inexistente.
    """
    from runtime_paths import repo_root as _runtime_repo_root
    return _runtime_repo_root()


def outputs_dir() -> Path:
    """Devuelve `<repo_root>/Agentes/outputs` resuelto absoluto."""
    return (repo_root() / Path(*OUTPUTS_SUBDIR)).resolve()


def default_html_path(ado_id: int) -> Path:
    """Path canónico del HTML para un ADO ID, sin validar existencia."""
    return outputs_dir() / str(ado_id) / "comment.html"


def find_agent_html(ado_id: int, hint: str | None = None) -> Path | None:
    """Localiza el HTML del agente para un ticket ADO.

    Prioridad:
      1. `hint` si se provee (path absoluto o relativo al repo_root). Debe
         caer dentro de `outputs_dir()` o lanza ValidationError.
      2. Path canónico `outputs_dir()/<ado_id>/comment.html`.

    Returns:
        Path absoluto si el archivo existe, None si no.

    Raises:
        ValidationError(code=PATH_ESCAPE) si el hint intenta salir de outputs_dir.
        ValidationError(code=INVALID_PATH) si el hint apunta a un dir/no-html.
    """
    candidate: Path
    if hint:
        candidate = _resolve_safe_path(hint)
    else:
        candidate = default_html_path(ado_id)

    return candidate if candidate.is_file() else None


def read_and_validate(
    ado_id: int, hint: str | None = None
) -> HtmlOutput:
    """Lee el HTML del agente para `ado_id` y valida sus invariantes.

    Args:
        ado_id: ID del work item ADO.
        hint: path opcional dado por el agente (se valida que caiga dentro de
              outputs_dir).

    Returns:
        HtmlOutput con el contenido y la metadata anexada (si existe).

    Raises:
        ValidationError con código en
        {NOT_FOUND, TOO_LARGE, EMPTY, SECRET_DETECTED, PATH_ESCAPE, INVALID_PATH}.
    """
    found = find_agent_html(ado_id, hint=hint)
    if found is None:
        raise ValidationError(
            code="NOT_FOUND",
            message=(
                f"No se encontró comment.html para ADO-{ado_id}. "
                f"Esperado en: {default_html_path(ado_id)} (o path hint)."
            ),
        )

    size = found.stat().st_size
    if size > MAX_HTML_BYTES:
        raise ValidationError(
            code="TOO_LARGE",
            message=f"HTML {size} bytes excede límite {MAX_HTML_BYTES} bytes",
        )

    html = found.read_text(encoding="utf-8", errors="replace")
    if not html.strip():
        raise ValidationError(code="EMPTY", message="HTML del agente está vacío")

    leak = _scan_secrets(html)
    if leak is not None:
        raise ValidationError(
            code="SECRET_DETECTED",
            message=f"HTML contiene posible secret (regex='{leak}')",
        )

    meta = _read_meta(found.parent / "comment.meta.json")

    return HtmlOutput(
        path=found,
        html=html,
        size_bytes=size,
        meta=meta,
        ado_id=ado_id,
    )


# ── Internos ──────────────────────────────────────────────────────────────────


def _resolve_safe_path(hint: str) -> Path:
    """Resuelve `hint` (relativo a repo_root o absoluto) y exige que esté
    contenido en outputs_dir(). Rechaza cualquier path escape.
    """
    p = Path(hint)
    if not p.is_absolute():
        p = repo_root() / p
    resolved = p.resolve()
    base = outputs_dir()
    try:
        resolved.relative_to(base)
    except ValueError:
        raise ValidationError(
            code="PATH_ESCAPE",
            message=(
                f"hint apunta fuera de {base}: {resolved}. "
                "Solo se aceptan paths dentro de Agentes/outputs/."
            ),
        )
    if resolved.exists() and resolved.is_dir():
        raise ValidationError(
            code="INVALID_PATH",
            message=f"hint apunta a un directorio, no a un archivo: {resolved}",
        )
    return resolved


def _read_meta(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("comment.meta.json inválido en %s — ignorando", path)
        return None


def _scan_secrets(html: str) -> str | None:
    """Retorna el nombre del patrón que matcheó, o None si está limpio."""
    for pattern in _SECRET_PATTERNS:
        if pattern.search(html):
            return pattern.pattern
    return None
