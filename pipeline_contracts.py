"""
pipeline_contracts.py — Contratos formales de input/output para cada etapa del pipeline.

Usa Pydantic para validación estricta. Si un agente devuelve algo que viola el contrato,
falla rápido y visible antes de enviar output defectuoso a la siguiente etapa.

Uso:
    from pipeline_contracts import PMOutputContract, DEVOutputContract, QAOutputContract
    contract = PMOutputContract(...)  # raises ValidationError si inválido
"""

from pydantic import BaseModel, field_validator
from typing import Optional


class PMOutputContract(BaseModel):
    """Contrato de output válido de la etapa PM."""
    incidente_lines: int
    analisis_lines: int
    arquitectura_lines: int
    tareas_lines: int
    has_pending_tasks: bool
    placeholders_count: int
    files_with_code_refs: list[str]

    @field_validator("placeholders_count")
    @classmethod
    def no_placeholders(cls, v: int) -> int:
        if v > 0:
            raise ValueError(f"PM output tiene {v} placeholder(s) sin reemplazar")
        return v


class DEVOutputContract(BaseModel):
    """Contrato de output válido de la etapa DEV."""
    files_modified: list[str]
    pending_tasks: int
    build_result: Optional[str] = None

    @field_validator("pending_tasks")
    @classmethod
    def no_pending(cls, v: int) -> int:
        if v > 0:
            raise ValueError(f"DEV dejó {v} tarea(s) PENDIENTE sin ejecutar")
        return v

    @field_validator("files_modified")
    @classmethod
    def at_least_one_file(cls, v: list) -> list:
        if not v:
            raise ValueError("DEV no reportó ningún archivo modificado")
        return v


class QAOutputContract(BaseModel):
    """Contrato de output válido de la etapa QA/Tester."""
    verdict: str
    cases_count: int
    findings: list[str]

    @field_validator("verdict")
    @classmethod
    def valid_verdict(cls, v: str) -> str:
        valid = {"APROBADO", "CON OBSERVACIONES", "RECHAZADO"}
        if v not in valid:
            raise ValueError(f"Veredicto '{v}' no válido. Debe ser uno de: {valid}")
        return v

    @field_validator("cases_count")
    @classmethod
    def min_cases(cls, v: int) -> int:
        if v < 1:
            raise ValueError("QA debe documentar al menos 1 caso de prueba")
        return v
