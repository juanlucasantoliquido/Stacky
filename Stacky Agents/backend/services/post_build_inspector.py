"""Plan 211 F1 — Inspector post-build (Capa B).

"Compila" no puede seguir ocultando un `PostBuildEvent` que copia binarios a la
carpeta de OTRO cliente. Este módulo parsea los project files que el Developer
construyó y emite hallazgos por efectos colaterales peligrosos.

PURO y determinista: lee archivos, aplica regex, devuelve dataclasses. Sin LLM,
sin red. Un archivo ilegible se saltea; nunca propaga.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_MAX_FILE_BYTES = 262144
_ABS_WIN_RE = re.compile(r"([A-Za-z]:[\\/]|\\\\[^\\/])")
_POST_BUILD_RE = re.compile(r"(?is)<PostBuildEvent>(.*?)</PostBuildEvent>")
_TARGET_AFTER_RE = re.compile(
    r'(?is)<Target\b[^>]*\b(?:AfterTargets|BeforeTargets)\s*=\s*"[^"]*Build[^"]*"[^>]*>(.*?)</Target>'
)
_COPY_RE = re.compile(
    r'(?is)<Copy\b[^>]*?(DestinationFolder|DestinationFiles)\s*=\s*"([^"]*)"'
)
_OUTPUT_RE = re.compile(r"(?is)<(OutputPath|OutDir)>([^<]*)</(?:OutputPath|OutDir)>")


@dataclass(frozen=True)
class InspectFinding:
    kind: str
    severity: str
    file: str
    detail: str
    evidence: str


def _read_head(path: str) -> str:
    try:
        with open(path, "rb") as fh:
            return fh.read(_MAX_FILE_BYTES).decode("utf-8", errors="replace")
    except OSError:
        return ""


def _is_abs(s) -> bool:
    return bool(_ABS_WIN_RE.search(s or ""))


def _contains_foreign(text, foreign_tokens):
    """Token de otro cliente por LÍMITE DE PALABRA (nunca substring crudo: 'crea'
    no puede matchear 'CrearCliente')."""
    low = (text or "").lower()
    for tok in (foreign_tokens or {}):
        if re.search(r"(?<![a-z0-9])" + re.escape(tok) + r"(?![a-z0-9])", low):
            return tok
    return None


def _trunc(s, n: int = 200) -> str:
    return (s or "").strip()[:n]


def inspect_projects(project_files: list, *, workspace_root: str,
                     foreign_tokens: dict | None = None) -> list:
    """Hallazgos de efectos colaterales de build. Nunca lanza."""
    foreign_tokens = foreign_tokens or {}
    out: list = []
    for path in project_files or []:
        text = _read_head(str(path))
        if not text:
            continue

        for contenido in _POST_BUILD_RE.findall(text):
            ajeno = _contains_foreign(contenido, foreign_tokens)
            if _is_abs(contenido) or ajeno:
                detalle = ("El evento post-build escribe fuera del proyecto"
                           + (f" y menciona a '{ajeno}' (otro cliente)" if ajeno else
                              " usando una ruta absoluta"))
                out.append(InspectFinding("post_build_event", "blocking", str(path),
                                          detalle, _trunc(contenido)))
            else:
                out.append(InspectFinding(
                    "post_build_event", "warning", str(path),
                    "Hay un evento post-build (rutas relativas).", _trunc(contenido)))

        for cuerpo in _TARGET_AFTER_RE.findall(text):
            ajeno = _contains_foreign(cuerpo, foreign_tokens)
            if _is_abs(cuerpo) or ajeno:
                detalle = ("Un Target atado al Build escribe fuera del proyecto"
                           + (f" y menciona a '{ajeno}' (otro cliente)" if ajeno else
                              " usando una ruta absoluta"))
                out.append(InspectFinding("after_targets", "blocking", str(path),
                                          detalle, _trunc(cuerpo)))
            elif "<Exec" in cuerpo or "<Copy" in cuerpo:
                out.append(InspectFinding(
                    "after_targets", "warning", str(path),
                    "Un Target atado al Build ejecuta o copia (rutas relativas).",
                    _trunc(cuerpo)))

        for _attr, destino in _COPY_RE.findall(text):
            ajeno = _contains_foreign(destino, foreign_tokens)
            if _is_abs(destino) or ajeno:
                detalle = ("Una tarea Copy apunta fuera del proyecto"
                           + (f" y menciona a '{ajeno}' (otro cliente)" if ajeno else
                              " usando una ruta absoluta"))
                out.append(InspectFinding("copy_task", "blocking", str(path),
                                          detalle, _trunc(destino)))
            else:
                out.append(InspectFinding(
                    "copy_task", "warning", str(path),
                    "Hay una tarea Copy (destino relativo).", _trunc(destino)))

        for _tag, valor in _OUTPUT_RE.findall(text):
            ajeno = _contains_foreign(valor, foreign_tokens)
            if ajeno:
                out.append(InspectFinding(
                    "foreign_output_path", "blocking", str(path),
                    f"La salida del build apunta a '{ajeno}' (otro cliente).",
                    _trunc(valor)))
            elif _is_abs(valor):
                out.append(InspectFinding(
                    "abs_output_path", "warning", str(path),
                    "La salida del build usa una ruta absoluta.", _trunc(valor)))
    return out


def findings_to_dicts(findings: list) -> list:
    """Shape que consume la seam de evidencia del gate de build."""
    return [{"kind": f.kind, "severity": f.severity, "file": f.file,
             "detail": f.detail} for f in findings or []]
