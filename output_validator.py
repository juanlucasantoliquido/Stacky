"""
output_validator.py — Validación de output de agentes entre etapas del pipeline.

Corre localmente (sin IA) antes de cada transición de etapa para detectar:
  - Placeholders no reemplazados ("_A completar por PM_")
  - Archivos incompletos (muy cortos o vacíos)
  - Tareas PENDIENTE no ejecutadas por DEV
  - Veredicto ausente en reporte QA

Si la validación falla, genera un {STAGE}_ERROR.flag con el detalle específico
de qué falta, evitando que la siguiente etapa trabaje con inputs defectuosos.

Uso:
    from output_validator import validate_stage_output, ValidationResult
    result = validate_stage_output("pm", ticket_folder, ticket_id)
    if not result.ok:
        # crear flag de error con result.issues_str()
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

# ── Constantes de validación ──────────────────────────────────────────────────

# Texto de placeholder que no debe quedar en ningún archivo post-PM
_PLACEHOLDER_PATTERNS = [
    "_A completar por PM_",
    "_A completar_",
    "<!-- TODO",
    "[COMPLETAR]",
    "[PENDIENTE DE ANÁLISIS]",
]

# Archivos que PM debe completar y mínimo de líneas esperadas.
# Los archivos marcados como requeridos generan ERROR si faltan o están incompletos.
# Los opcionales solo generan WARNING.
_PM_REQUIRED_FILES = {
    "INCIDENTE.md":             5,
    "ANALISIS_TECNICO.md":     10,
    "ARQUITECTURA_SOLUCION.md": 8,
    "TAREAS_DESARROLLO.md":    10,
}

# Archivos opcionales: su ausencia es una advertencia, no un error bloqueante.
# No todos los tickets tienen queries SQL ni notas de implementación separadas.
_PM_OPTIONAL_FILES = {
    "QUERIES_ANALISIS.sql":    3,
    "NOTAS_IMPLEMENTACION.md": 5,
}

# Mínimo de líneas en DEV_COMPLETADO.md
_DEV_COMPLETADO_MIN_LINES = 5

# Mínimo de casos en TESTER_COMPLETADO.md
_QA_MIN_LINES = 10

# Veredictos válidos en el reporte QA
_QA_VERDICTS = ["APROBADO", "CON OBSERVACIONES", "RECHAZADO"]


@dataclass
class ValidationResult:
    ok: bool
    stage: str
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def issues_str(self) -> str:
        """Retorna las issues como string para el flag de error."""
        if not self.issues:
            return "Validación falló sin issues específicos."
        return "\n".join(f"- {i}" for i in self.issues)

    def __str__(self) -> str:
        status = "OK" if self.ok else "FALLO"
        lines = [f"Validación {self.stage.upper()}: {status}"]
        for i in self.issues:
            lines.append(f"  ERROR: {i}")
        for w in self.warnings:
            lines.append(f"  WARN:  {w}")
        return "\n".join(lines)


# ── API pública ───────────────────────────────────────────────────────────────

def validate_stage_output(stage: str, ticket_folder: str,
                           ticket_id: str = "") -> ValidationResult:
    """
    Valida el output de una etapa antes de avanzar a la siguiente.

    stage: "pm" | "dev" | "tester"
    Retorna ValidationResult con ok=True si la validación pasó.
    """
    validators = {
        "pm":     _validate_pm,
        "dev":    _validate_dev,
        "tester": _validate_tester,
    }
    fn = validators.get(stage)
    if fn is None:
        return ValidationResult(ok=True, stage=stage,
                                warnings=[f"No hay validador para stage '{stage}'"])
    return fn(ticket_folder, ticket_id)


def write_error_flag_if_invalid(result: ValidationResult,
                                 ticket_folder: str) -> bool:
    """
    Si la validación falló, crea {STAGE}_ERROR.flag con el detalle.
    Retorna True si se creó el flag (= validación falló).
    """
    if result.ok:
        return False
    flag_name = f"{result.stage.upper()}_ERROR.flag"
    flag_path = os.path.join(ticket_folder, flag_name)
    try:
        with open(flag_path, "w", encoding="utf-8") as fh:
            fh.write(f"Validación automática de output falló:\n\n")
            fh.write(result.issues_str())
    except Exception as e:
        import logging
        logging.getLogger("mantis.validator").error(
            "No se pudo escribir %s: %s", flag_path, e
        )
    return True


# ── Validadores por etapa ─────────────────────────────────────────────────────

def _validate_pm(ticket_folder: str, ticket_id: str) -> ValidationResult:
    """Valida que PM completó los archivos requeridos sin placeholders."""
    import time as _time

    issues   = []
    warnings = []

    # Pequeño delay para evitar race condition: el agente puede crear PM_COMPLETADO.flag
    # mientras todavía está escribiendo los últimos archivos.
    _time.sleep(2)

    def _check_file(fname: str, min_lines: int, is_required: bool) -> None:
        fpath = os.path.join(ticket_folder, fname)

        if not os.path.exists(fpath):
            if is_required:
                issues.append(f"{fname}: archivo no encontrado")
            else:
                warnings.append(f"{fname}: archivo no generado (opcional)")
            return

        try:
            content = Path(fpath).read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            if is_required:
                issues.append(f"{fname}: no se pudo leer ({e})")
            else:
                warnings.append(f"{fname}: no se pudo leer ({e})")
            return

        lines = [l for l in content.splitlines() if l.strip()]

        if len(lines) < min_lines:
            msg = f"{fname}: muy pocas líneas ({len(lines)} de {min_lines} mínimas)"
            if is_required:
                issues.append(msg)
            else:
                warnings.append(msg)

        # ¿Quedaron placeholders?
        for placeholder in _PLACEHOLDER_PATTERNS:
            if placeholder.lower() in content.lower():
                if is_required:
                    issues.append(f"{fname}: contiene placeholder '{placeholder}'")
                else:
                    warnings.append(f"{fname}: contiene placeholder '{placeholder}'")
                break

    for fname, min_lines in _PM_REQUIRED_FILES.items():
        _check_file(fname, min_lines, is_required=True)

    for fname, min_lines in _PM_OPTIONAL_FILES.items():
        _check_file(fname, min_lines, is_required=False)

    # TAREAS_DESARROLLO.md debe tener al menos 1 tarea PENDIENTE
    tareas_path = os.path.join(ticket_folder, "TAREAS_DESARROLLO.md")
    if os.path.exists(tareas_path):
        tareas_content = Path(tareas_path).read_text(encoding="utf-8", errors="replace")
        if "PENDIENTE" not in tareas_content.upper():
            issues.append(
                "TAREAS_DESARROLLO.md: no contiene ninguna tarea marcada como PENDIENTE"
            )

    # ARQUITECTURA_SOLUCION.md debe mencionar al menos 1 archivo con ruta
    arq_path = os.path.join(ticket_folder, "ARQUITECTURA_SOLUCION.md")
    if os.path.exists(arq_path):
        arq_content = Path(arq_path).read_text(encoding="utf-8", errors="replace")
        # Buscar algo que parezca una ruta de archivo (.cs, .aspx, .sql, .vb)
        has_file_ref = bool(re.search(
            r'\b\w[\w/\\]+\.(?:cs|aspx|aspx\.cs|sql|vb|config)\b',
            arq_content, re.IGNORECASE
        ))
        if not has_file_ref:
            warnings.append(
                "ARQUITECTURA_SOLUCION.md: no menciona archivos específicos del codebase"
            )

    return ValidationResult(
        ok=len(issues) == 0,
        stage="pm",
        issues=issues,
        warnings=warnings,
    )


def _validate_dev(ticket_folder: str, ticket_id: str) -> ValidationResult:
    """Valida que DEV generó DEV_COMPLETADO.md con contenido real."""
    issues   = []
    warnings = []

    dev_path = os.path.join(ticket_folder, "DEV_COMPLETADO.md")

    if not os.path.exists(dev_path):
        issues.append("DEV_COMPLETADO.md: archivo no encontrado")
        return ValidationResult(ok=False, stage="dev", issues=issues)

    content = Path(dev_path).read_text(encoding="utf-8", errors="replace")
    lines   = [l for l in content.splitlines() if l.strip()]

    if len(lines) < _DEV_COMPLETADO_MIN_LINES:
        issues.append(
            f"DEV_COMPLETADO.md: muy pocas líneas ({len(lines)} de "
            f"{_DEV_COMPLETADO_MIN_LINES} mínimas)"
        )

    # Debe mencionar al menos 1 archivo modificado
    has_file = bool(re.search(
        r'\b\w[\w/\\]+\.(?:cs|aspx|aspx\.cs|sql|vb|config)\b',
        content, re.IGNORECASE
    ))
    if not has_file:
        issues.append(
            "DEV_COMPLETADO.md: no menciona archivos modificados del codebase"
        )

    # Verificar que TAREAS_DESARROLLO.md no tenga PENDIENTE sin completar
    tareas_path = os.path.join(ticket_folder, "TAREAS_DESARROLLO.md")
    if os.path.exists(tareas_path):
        tareas = Path(tareas_path).read_text(encoding="utf-8", errors="replace")
        # Buscar líneas con PENDIENTE que no estén en comentarios o histórico
        pendientes = [
            l.strip() for l in tareas.splitlines()
            if "PENDIENTE" in l.upper()
            and not l.strip().startswith("#")
            and not l.strip().startswith("<!--")
        ]
        if pendientes:
            issues.append(
                f"TAREAS_DESARROLLO.md: quedan {len(pendientes)} tarea(s) en estado PENDIENTE"
            )

    return ValidationResult(
        ok=len(issues) == 0,
        stage="dev",
        issues=issues,
        warnings=warnings,
    )


def _validate_tester(ticket_folder: str, ticket_id: str) -> ValidationResult:
    """Valida que QA generó TESTER_COMPLETADO.md con veredicto explícito."""
    issues   = []
    warnings = []

    tester_path = os.path.join(ticket_folder, "TESTER_COMPLETADO.md")

    if not os.path.exists(tester_path):
        issues.append("TESTER_COMPLETADO.md: archivo no encontrado")
        return ValidationResult(ok=False, stage="tester", issues=issues)

    content = Path(tester_path).read_text(encoding="utf-8", errors="replace")
    lines   = [l for l in content.splitlines() if l.strip()]

    if len(lines) < _QA_MIN_LINES:
        issues.append(
            f"TESTER_COMPLETADO.md: muy pocas líneas ({len(lines)} de "
            f"{_QA_MIN_LINES} mínimas)"
        )

    # Debe tener veredicto explícito
    has_verdict = any(v in content.upper() for v in _QA_VERDICTS)
    if not has_verdict:
        issues.append(
            "TESTER_COMPLETADO.md: no contiene veredicto explícito "
            "(APROBADO / CON OBSERVACIONES / RECHAZADO)"
        )

    # Detectar si el veredicto es aprobado (para feedback loop M-01)
    result = ValidationResult(
        ok=len(issues) == 0,
        stage="tester",
        issues=issues,
        warnings=warnings,
    )
    # Agregar metadata del veredicto al resultado
    result.verdict        = _extract_verdict(content)
    result.has_issues_qa  = result.verdict in ("CON OBSERVACIONES", "RECHAZADO")
    result.qa_findings    = _extract_qa_findings(content) if result.has_issues_qa else []

    return result


# ── Helpers internos ──────────────────────────────────────────────────────────

def _extract_verdict(content: str) -> str:
    """Extrae el veredicto de TESTER_COMPLETADO.md."""
    upper = content.upper()
    for v in _QA_VERDICTS:
        if v in upper:
            return v
    return "DESCONOCIDO"


def _extract_qa_findings(content: str) -> list[str]:
    """
    Extrae lista de issues/observaciones de TESTER_COMPLETADO.md.
    Busca secciones de observaciones, rechazos o issues.
    """
    findings = []
    in_section = False
    for line in content.splitlines():
        stripped = line.strip()
        # Detectar sección de observaciones
        if re.match(r'^#+\s*(observaciones|issues|problemas|rechazos|hallazgos)',
                    stripped, re.IGNORECASE):
            in_section = True
            continue
        # Salir de sección al encontrar otro heading
        if in_section and re.match(r'^#+\s', stripped):
            in_section = False
        # Capturar ítems de lista dentro de la sección
        if in_section and stripped.startswith(("-", "*", "•")) and len(stripped) > 3:
            findings.append(stripped.lstrip("-*• ").strip())

    return findings[:10]  # máximo 10 findings para no saturar el prompt de rework
