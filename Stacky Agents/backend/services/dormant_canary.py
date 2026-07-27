"""services/dormant_canary.py — Plan 255 F6.

Canario de features DORMIDAS: lo inverso a una huella de regresión.

Por qué existe
--------------
El hallazgo central del plan 255 no es que el `resume` tuviera un bug de
SQLAlchemy: es que estuvo **9 días muerto con las flags en ON y nadie se
enteró**, porque Stacky mide que las cosas **fallen**, no que hayan
**funcionado**. Una huella (`services/error_fingerprints.py`) alarma cuando
aparece un patrón malo; nada alarmaba cuando un patrón **bueno dejaba de
aparecer**. Los tres mecanismos que la auditoría encontró rotos —resume, cosecha
de telemetría y sweep de aprendizaje ADO— tienen exactamente esa forma: caros,
gateados por flags que el operador dejó en ON, y mudos cuando funcionan.

Reglas duras
------------
- **AVISA, NUNCA ARREGLA.** No reintenta, no re-habilita, no toca config, no
  escribe un solo archivo. El canario le da al operador un hecho; la decisión
  es suya (human-in-the-loop innegociable).
- **`apagado` ≠ `dormido`.** Si las `gate_flags` están OFF, el operador lo apagó
  a propósito: eso no es una alarma. La alarma es *flag ON + cero éxitos en
  `max_silent_days`*. Esta distinción es lo que evita que el canario sea ruido.
- **`sin_datos` ≠ `dormido`.** Sin log suficiente para cubrir la ventana no se
  afirma que algo esté muerto. Nunca se concluye sin evidencia.
- **Cero costo ocioso.** Se evalúa BAJO DEMANDA al pegarle al endpoint, no en un
  loop. Reusa el tail acotado de `error_fingerprints` y corta apenas encontró un
  éxito para cada canario: el caso normal lee UN archivo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from services.error_fingerprints import _BOOT_SCAN_TAIL_BYTES

__all__ = ["CanarySpec", "CANARIES", "check_canaries", "STATUSES"]

STATUSES = ("ok", "dormido", "apagado", "sin_datos")

_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})")
_LOG_NAME_RE = re.compile(r"stacky-(\d{4}-\d{2}-\d{2})\.log$")


@dataclass(frozen=True)
class CanarySpec:
    id: str                        # slug estable
    label: str                     # texto para la UI, en español
    success_pattern: str           # regex de la línea que SOLO aparece con ÉXITO
    gate_flags: tuple[str, ...]    # flags que deben estar ON para esperar actividad
    max_silent_days: int           # días sin éxito antes de avisar
    hint: str                      # qué mirar; NUNCA una acción automática


# Los acentos van como `.` a propósito: un log reescrito con otra codificación no
# puede convertir un canario en un falso "dormido".
CANARIES: tuple[CanarySpec, ...] = (
    CanarySpec(
        id="resume_efectivo",
        label="Reanudación de sesión previa (Claude Code CLI / Codex CLI)",
        # Cubre las tres formas del camino de éxito: la de harness/resume.py y la
        # de cada call-site (el de claude no dice "sesión previa=", dice
        # "resume de sesión previa").
        success_pattern=(
            r"resume\s+\S+:\s+sesi.n=|resume:\s+sesi.n\s+previa=|resume\s+de\s+sesi.n\s+previa"
        ),
        gate_flags=("CLAUDE_CODE_CLI_RESUME_ENABLED", "CODEX_CLI_RESUME_ENABLED"),
        max_silent_days=3,
        hint=("Ninguna corrida reanudó una sesión previa. Mirá el historial buscando "
              "'arranque en frío' y revisá la lista de proyectos habilitados para "
              "reanudar. No se cambió ninguna configuración."),
    ),
    CanarySpec(
        id="telemetry_harvest",
        label="Cosecha de telemetría histórica desde los artefactos en disco",
        success_pattern=r"plan199 autoscan: discovered=\d+ backfilled=\d+",
        gate_flags=("STACKY_TELEMETRY_HARVEST_ENABLED",
                    "STACKY_TELEMETRY_HARVEST_AUTOSCAN_ENABLED"),
        max_silent_days=3,
        hint=("La cosecha no dejó ni un resultado. Mirá el historial buscando "
              "'plan199 autoscan' y confirmá que las carpetas de sesiones de los "
              "CLI existen en este equipo."),
    ),
    CanarySpec(
        id="ado_edit_learning_sweep",
        label="Aprendizaje de las ediciones humanas en el tracker",
        success_pattern=r"ado edit learning: WI .* => lecci.n nueva",
        gate_flags=(),
        max_silent_days=7,
        hint=("Hace días que no se aprende nada de una edición humana. Puede ser "
              "normal (nadie editó) o puede ser el sweep inerte: buscá "
              "'sweep_recent_runs: fallo ESTRUCTURAL' en el historial."),
    ),
)


# ── Lectura del log (acotada, bajo demanda) ───────────────────────────────────


def _log_files(limit: int = 10) -> list[Path]:
    """Los `stacky-*.log` más recientes primero. Nunca lanza."""
    try:
        from services.local_file_logging import logs_dir

        archivos = [p for p in logs_dir().glob("stacky-*.log") if p.is_file()]
    except Exception:  # noqa: BLE001
        return []
    archivos.sort(key=lambda p: p.name, reverse=True)
    return archivos[:limit]


def _tail(path: Path) -> str:
    """Tail acotado, con el MISMO límite que el boot-scan de huellas."""
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > _BOOT_SCAN_TAIL_BYTES:
                fh.seek(size - _BOOT_SCAN_TAIL_BYTES)
            return fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _fecha_de_archivo(path: Path) -> datetime | None:
    m = _LOG_NAME_RE.search(path.name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d")
    except ValueError:
        return None


def _ultimo_exito(texto: str, patron: re.Pattern, respaldo: datetime | None):
    """Timestamp de la ÚLTIMA línea que matchea, o `respaldo` si no tiene sello."""
    for linea in reversed(texto.splitlines()):
        if not patron.search(linea):
            continue
        m = _TS_RE.match(linea.strip())
        if m:
            try:
                return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return respaldo
        return respaldo
    return None


def _flag_on(key: str) -> bool:
    try:
        from config import config

        return bool(getattr(config, key, False))
    except Exception:  # noqa: BLE001
        return False


# ── API pública ───────────────────────────────────────────────────────────────


def check_canaries(now=None, *, canaries=None, log_files=None) -> list[dict]:
    """Estado de cada mecanismo vigilado. READ-ONLY: NO ARREGLA NADA.

    [{'id','label','status','last_success_at','days_silent','gated_off','hint'}]
    status ∈ {'ok', 'dormido', 'apagado', 'sin_datos'}.
    """
    ahora = now or datetime.now()
    specs = tuple(canaries if canaries is not None else CANARIES)
    ventana_max = max((s.max_silent_days for s in specs), default=1)

    archivos = list(log_files if log_files is not None
                    else _log_files(limit=ventana_max + 1))

    patrones = {s.id: re.compile(s.success_pattern) for s in specs}
    ultimos: dict[str, datetime] = {}

    # Días efectivamente cubiertos por los archivos disponibles: sin esto no se
    # puede distinguir "no pasó" de "no hay con qué mirar".
    fechas = {f.date() for f in (_fecha_de_archivo(p) for p in archivos) if f}
    dias_cubiertos = len(fechas) if fechas else len(archivos)

    pendientes = {s.id for s in specs}
    for path in archivos:
        if not pendientes:
            break  # el caso normal: todo tuvo éxito en el archivo más reciente
        texto = _tail(path)
        if not texto:
            continue
        respaldo = _fecha_de_archivo(path)
        for spec in specs:
            if spec.id not in pendientes:
                continue
            hallado = _ultimo_exito(texto, patrones[spec.id], respaldo)
            if hallado is not None:
                ultimos[spec.id] = hallado
                pendientes.discard(spec.id)

    filas: list[dict] = []
    for spec in specs:
        gated_off = bool(spec.gate_flags) and not any(_flag_on(f) for f in spec.gate_flags)
        ultimo = ultimos.get(spec.id)
        dias = (ahora - ultimo).days if ultimo else None

        if gated_off:
            estado = "apagado"
        elif ultimo is not None:
            estado = "ok" if (dias or 0) <= spec.max_silent_days else "dormido"
        elif dias_cubiertos < spec.max_silent_days:
            estado = "sin_datos"
        else:
            estado = "dormido"

        filas.append({
            "id": spec.id,
            "label": spec.label,
            "status": estado,
            "last_success_at": ultimo.isoformat() if ultimo else None,
            "days_silent": dias,
            "gated_off": gated_off,
            "max_silent_days": spec.max_silent_days,
            "hint": spec.hint,
        })
    return filas
