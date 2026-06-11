"""artifact_validator.py — Validación sincrónica de artifacts de agente (F1.3/F1.4).

Valida los archivos que los agentes escriben por convención en
`Agentes/outputs/` ANTES de que el run cierre, para poder devolver el error
exacto al agente por stdin (loop de autocorrección, F1.3) o en el momento de
la escritura (hook PostToolUse, F1.4).

Causa raíz confirmada de "crea archivos pero no la task":
  - pending-task.json con JSON inválido, y/o
  - mismatch entre el número ORDINAL del RF/épica y el ADO id REAL
    (directorio `epic-<n>` y/o campo `epic_id` apuntando a un id inexistente).

Este módulo NO muta nada: solo lee disco y (best-effort) consulta la DB para
verificar que el epic_id declarado exista como ticket real. output_watcher y
agent_completion siguen siendo el fallback de cierre — acá solo se detecta
temprano.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("stacky.artifact_validator")

PENDING_TASK_FILENAME = "pending-task.json"
COMMENT_HTML_FILENAME = "comment.html"

# Copia local del contrato canónico (api/tickets.py:_PENDING_TASK_REQUIRED_FIELDS).
# Se intenta importar la fuente canónica en runtime (lazy, sin ciclo de import);
# este set es el fallback si api.tickets no está importable (p.ej. tests unitarios).
_FALLBACK_REQUIRED_FIELDS = frozenset({
    "generated_at", "generated_by", "epic_id", "rf_id",
    "title", "description_html", "plan_de_pruebas_path",
    "parent_link_type", "status",
})
_FALLBACK_PENDING_STATUSES = frozenset({"pending_manual_creation", "pending", "consumed"})

_EPIC_DIR_RE = re.compile(r"^epic-(\d+)$", re.IGNORECASE)


def _required_fields() -> frozenset[str]:
    try:
        from api.tickets import _PENDING_TASK_REQUIRED_FIELDS  # noqa: PLC0415
        return frozenset(_PENDING_TASK_REQUIRED_FIELDS)
    except Exception:
        return _FALLBACK_REQUIRED_FIELDS


def _allowed_statuses() -> frozenset[str]:
    try:
        from api.tickets import _PENDING_TASK_STATUS_ALLOWED  # noqa: PLC0415
        return frozenset(_PENDING_TASK_STATUS_ALLOWED)
    except Exception:
        return _FALLBACK_PENDING_STATUSES


def _ticket_exists(ado_id: int) -> bool | None:
    """True/False si la DB responde; None si no se puede consultar (skip rule)."""
    try:
        from db import session_scope  # noqa: PLC0415
        from models import Ticket  # noqa: PLC0415

        with session_scope() as session:
            return (
                session.query(Ticket.id).filter(Ticket.ado_id == int(ado_id)).first()
                is not None
            )
    except Exception:
        logger.debug("artifact_validator: DB no consultable para ADO-%s", ado_id, exc_info=True)
        return None


# ── Resultados tipados ────────────────────────────────────────────────────────


@dataclass
class ArtifactValidation:
    path: str
    kind: str                       # "pending_task" | "comment_html" | "other"
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "kind": self.kind,
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class ArtifactReport:
    """Reporte agregado de los artifacts de un run (F1.3)."""

    artifacts: list[ArtifactValidation] = field(default_factory=list)

    @property
    def checked(self) -> int:
        return len(self.artifacts)

    @property
    def invalid(self) -> list[ArtifactValidation]:
        return [a for a in self.artifacts if not a.valid]

    @property
    def ok(self) -> bool:
        return not self.invalid

    def to_dict(self) -> dict:
        return {
            "checked": self.checked,
            "ok": self.ok,
            "invalid_count": len(self.invalid),
            "artifacts": [a.to_dict() for a in self.artifacts],
        }


# ── Validadores por tipo de archivo ───────────────────────────────────────────


def _epic_id_from_path(path: Path) -> int | None:
    """Extrae el id del directorio `epic-<n>` ancestro del pending-task.json."""
    for parent in path.parents:
        m = _EPIC_DIR_RE.match(parent.name)
        if m:
            return int(m.group(1))
    return None


def validate_pending_task_file(path: Path | str, *, check_db: bool = True) -> ArtifactValidation:
    """Valida un pending-task.json: JSON parseable + schema + ADO id real vs ordinal."""
    p = Path(path)
    result = ArtifactValidation(path=str(p), kind="pending_task", valid=True)

    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as exc:
        result.valid = False
        result.errors.append(f"no se pudo leer el archivo: {exc}")
        return result

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        result.valid = False
        result.errors.append(
            f"JSON inválido (línea {exc.lineno}, col {exc.colno}): {exc.msg}. "
            "Reescribí el archivo completo con JSON válido (sin comentarios ni comas finales)."
        )
        return result

    if not isinstance(payload, dict):
        result.valid = False
        result.errors.append("el JSON raíz debe ser un objeto, no una lista/escalar")
        return result

    # Schema: campos requeridos
    missing = sorted(_required_fields() - set(payload.keys()))
    if missing:
        result.valid = False
        result.errors.append(f"faltan campos requeridos: {', '.join(missing)}")

    # status dentro del contrato
    status = payload.get("status")
    if status is not None and status not in _allowed_statuses():
        result.valid = False
        result.errors.append(
            f"status '{status}' inválido; usar 'pending_manual_creation'"
        )

    # epic_id: entero + coherencia con el directorio epic-<n>
    epic_id_raw = payload.get("epic_id")
    epic_id: int | None = None
    if epic_id_raw is not None:
        try:
            epic_id = int(epic_id_raw)
        except (TypeError, ValueError):
            result.valid = False
            result.errors.append(f"epic_id '{epic_id_raw}' no es un entero")

    dir_epic_id = _epic_id_from_path(p)
    if epic_id is not None and dir_epic_id is not None and epic_id != dir_epic_id:
        result.valid = False
        result.errors.append(
            f"mismatch: el directorio es epic-{dir_epic_id} pero epic_id={epic_id}. "
            "Ambos deben ser el ADO id REAL del Epic (no el número ordinal del RF)."
        )

    # ADO id real vs ordinal: el epic_id declarado debe existir como ticket real.
    if check_db and epic_id is not None:
        exists = _ticket_exists(epic_id)
        if exists is False:
            result.valid = False
            result.errors.append(
                f"epic_id={epic_id} no corresponde a ningún work item conocido. "
                "Probablemente usaste el número ordinal (1, 2, 3…) en vez del "
                "ADO id real del Epic. Corregí epic_id y el nombre del directorio epic-<ADO_ID>."
            )

    # plan_de_pruebas_path referenciado: warning si no existe (no bloquea)
    plan_rel = payload.get("plan_de_pruebas_path")
    if isinstance(plan_rel, str) and plan_rel.strip():
        plan_path = Path(plan_rel)
        if not plan_path.is_absolute():
            plan_path = p.parent / plan_rel
        if not plan_path.exists():
            result.warnings.append(
                f"plan_de_pruebas_path referencia un archivo inexistente: {plan_rel}"
            )

    return result


def validate_comment_html_file(path: Path | str) -> ArtifactValidation:
    """Valida un comment.html: existente y no vacío."""
    p = Path(path)
    result = ArtifactValidation(path=str(p), kind="comment_html", valid=True)
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        result.valid = False
        result.errors.append(f"no se pudo leer el archivo: {exc}")
        return result
    if not content.strip():
        result.valid = False
        result.errors.append("comment.html está vacío; debe contener el comentario HTML completo")
    elif "<" not in content:
        result.warnings.append("comment.html no parece contener HTML (sin tags)")
    return result


def validate_artifact_path(path: Path | str, *, check_db: bool = True) -> ArtifactValidation:
    """Clasifica y valida un artifact por su nombre (entrada del hook/endpoint F1.4)."""
    p = Path(path)
    name = p.name.lower()
    if name == PENDING_TASK_FILENAME:
        return validate_pending_task_file(p, check_db=check_db)
    if name == COMMENT_HTML_FILENAME:
        return validate_comment_html_file(p)
    return ArtifactValidation(path=str(p), kind="other", valid=True)


# ── Reporte agregado por run (F1.3) ───────────────────────────────────────────


def _default_outputs_root() -> Path:
    from services.agent_html_output import outputs_dir  # noqa: PLC0415
    return outputs_dir()


def validate_run_artifacts(
    *,
    ado_id: int,
    outputs_root: Path | str | None = None,
    since_epoch: float | None = None,
    check_db: bool = True,
) -> ArtifactReport:
    """Valida los artifacts presentes para un ticket/épica.

    Política F1.3: solo se validan artifacts que EXISTEN. La ausencia no genera
    corrección (no todos los agentes producen artifacts ADO; output_watcher y
    agent_completion siguen siendo el fallback de cierre). El caso confirmado
    "crea archivos pero no la task" es siempre artifact-presente-pero-inválido.

    Args:
        ado_id: ADO id real del ticket/épica del run.
        outputs_root: override del directorio `Agentes/outputs` (tests).
        since_epoch: si se pasa (epoch seconds, comparar contra st_mtime),
            también se escanean pending-task.json escritos después de ese
            instante en CUALQUIER carpeta `epic-*` — esto caza el caso del
            agente que nombró el directorio con el ordinal (epic-1) en vez
            del ADO id real.
        check_db: verificar epic_id contra tickets reales (best-effort).
    """
    report = ArtifactReport()
    try:
        root = Path(outputs_root) if outputs_root is not None else _default_outputs_root()
    except Exception:
        logger.debug("artifact_validator: outputs root no resolvible", exc_info=True)
        return report
    if not root.exists():
        return report

    seen: set[str] = set()

    # Modo B — comentario ADO
    comment = root / str(ado_id) / COMMENT_HTML_FILENAME
    if comment.exists():
        report.artifacts.append(validate_comment_html_file(comment))
        seen.add(str(comment.resolve()))

    # Modo A — pending-task.json del Epic propio
    epic_dir = root / f"epic-{ado_id}"
    pending_files: list[Path] = []
    if epic_dir.exists():
        pending_files.extend(epic_dir.glob(PENDING_TASK_FILENAME))
        pending_files.extend(epic_dir.glob(f"*/{PENDING_TASK_FILENAME}"))

    # Pending-task escritos durante el run en OTRAS carpetas epic-* (ordinal).
    if since_epoch is not None:
        for other in root.glob(f"epic-*/**/{PENDING_TASK_FILENAME}"):
            try:
                if other.stat().st_mtime >= since_epoch:
                    pending_files.append(other)
            except OSError:
                continue

    for pt in pending_files:
        key = str(pt.resolve())
        if key in seen:
            continue
        seen.add(key)
        report.artifacts.append(validate_pending_task_file(pt, check_db=check_db))

    return report
