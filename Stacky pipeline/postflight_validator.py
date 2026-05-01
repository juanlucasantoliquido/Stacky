"""
postflight_validator.py — A3: validación post-etapa antes de transicionar
a estado *_completado.

Se invoca desde pipeline_watcher._advance_state. Si valida OK, la transición
sigue normalmente. Si falla, devuelve la razón y el caller debe marcar
error_{stage} en lugar de avanzar.

Reglas por etapa:
  - PM:     existen los 6 archivos PM y ninguno contiene placeholder, todos
            con tamaño > MIN_BYTES.
  - DEV:    existe DEV_COMPLETADO.md > 100 bytes, snapshots/dev_files.txt
            no vacío (no "(sin cambios)").
  - TESTER: existe TESTER_COMPLETADO.md y se puede extraer un veredicto
            APROBADO/RECHAZADO/CON OBSERVACIONES.
"""

import logging
import os

logger = logging.getLogger("stacky.postflight")

PLACEHOLDER_MARKERS = ("_A completar por PM_", "A completar por PM")
MIN_PM_BYTES        = 200
MIN_DEV_BYTES       = 100

PM_REQUIRED_FILES = [
    "INCIDENTE.md",
    "ANALISIS_TECNICO.md",
    "ARQUITECTURA_SOLUCION.md",
    "TAREAS_DESARROLLO.md",
    "QUERIES_ANALISIS.sql",
    "NOTAS_IMPLEMENTACION.md",
]


class PostflightResult:
    __slots__ = ("ok", "stage", "reason")

    def __init__(self, ok: bool, stage: str, reason: str = ""):
        self.ok     = ok
        self.stage  = stage
        self.reason = reason

    def __bool__(self) -> bool:
        return self.ok

    def __repr__(self) -> str:
        return f"PostflightResult(ok={self.ok}, stage={self.stage!r}, reason={self.reason!r})"


def _read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def _validate_pm(folder: str) -> PostflightResult:
    missing  = []
    empty    = []
    placeholder_in = []
    for fname in PM_REQUIRED_FILES:
        fpath = os.path.join(folder, fname)
        if not os.path.exists(fpath):
            missing.append(fname)
            continue
        try:
            size = os.path.getsize(fpath)
        except OSError:
            missing.append(fname)
            continue
        if size < MIN_PM_BYTES:
            empty.append(f"{fname} ({size}B)")
            continue
        content = _read_text(fpath)
        if any(marker in content for marker in PLACEHOLDER_MARKERS):
            placeholder_in.append(fname)
    if missing:
        return PostflightResult(False, "pm", f"archivos ausentes: {', '.join(missing)}")
    if empty:
        return PostflightResult(False, "pm",
                                f"archivos por debajo de {MIN_PM_BYTES}B: {', '.join(empty)}")
    if placeholder_in:
        return PostflightResult(False, "pm",
                                f"placeholder sin completar en: {', '.join(placeholder_in)}")
    return PostflightResult(True, "pm")


def _validate_dev(folder: str) -> PostflightResult:
    dev_md = os.path.join(folder, "DEV_COMPLETADO.md")
    if not os.path.exists(dev_md):
        return PostflightResult(False, "dev", "DEV_COMPLETADO.md ausente")
    try:
        size = os.path.getsize(dev_md)
    except OSError:
        size = 0
    if size < MIN_DEV_BYTES:
        return PostflightResult(False, "dev",
                                f"DEV_COMPLETADO.md por debajo de {MIN_DEV_BYTES}B ({size}B)")
    files_txt = os.path.join(folder, "snapshots", "dev_files.txt")
    if os.path.exists(files_txt):
        content = _read_text(files_txt).strip()
        useful = [ln for ln in content.splitlines()
                  if ln.strip() and not ln.lstrip().startswith("#")
                  and ln.strip() != "(sin cambios)"]
        if not useful:
            return PostflightResult(False, "dev",
                                    "snapshots/dev_files.txt sin archivos modificados")
    # Si no hay snapshot todavía no es bloqueante (puede generarse async).
    return PostflightResult(True, "dev")


def _validate_tester(folder: str) -> PostflightResult:
    tester_md = os.path.join(folder, "TESTER_COMPLETADO.md")
    if not os.path.exists(tester_md):
        return PostflightResult(False, "tester", "TESTER_COMPLETADO.md ausente")
    content = _read_text(tester_md).upper()
    for verdict in ("RECHAZADO", "CON OBSERVACIONES", "APROBADO"):
        if verdict in content:
            return PostflightResult(True, "tester")
    return PostflightResult(False, "tester",
                            "veredicto no detectado (esperado APROBADO/RECHAZADO/CON OBSERVACIONES)")


_VALIDATORS = {
    "pm":     _validate_pm,
    "dev":    _validate_dev,
    "tester": _validate_tester,
}


def validate_stage_outputs(folder: str, stage: str) -> PostflightResult:
    """Punto de entrada único. `stage` ∈ {pm, dev, tester}.
    Para sub-etapas (dev_rework, etc.) o etapas no listadas, devuelve OK
    para no romper transiciones legítimas no cubiertas."""
    if not folder or not os.path.isdir(folder):
        return PostflightResult(False, stage, f"carpeta del ticket no existe: {folder}")
    validator = _VALIDATORS.get(stage)
    if validator is None:
        return PostflightResult(True, stage)  # no aplica → pasar
    try:
        return validator(folder)
    except Exception as e:
        logger.exception("[POSTFLIGHT] error inesperado validando %s/%s", folder, stage)
        return PostflightResult(False, stage, f"error inesperado en validador: {e}")
