"""
model.py — Modelo interno del Batch Test Generator.

Representa la estructura de un proceso Batch con sus sub-procesos,
clases de negocio y metadatos necesarios para generar tests unitarios.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class SubprocType(str, Enum):
    """Variante de cómo se declara y llama un sub-proceso."""
    CONST_INT   = "const_int"    # private const int NOMBRE = N; + HayQueEjecSubProceso(NOMBRE)
    ENUM        = "enum"         # enum Subproceso { NOMBRE = N }  + HayQueEjecSubProceso(Subproceso.NOMBRE)
    GLOBAL_FLAG = "global_flag"  # cGlobales.nEjecutaXxx == 1  (Motor)
    UNKNOWN     = "unknown"


@dataclass
class BizMethod:
    """Un método público de la clase de negocio relevante para tests."""
    name: str                       # "RetroalimentarCampaniaTelef"
    return_type: str                # "bool" | "int" | "void" | "DataTable" | ...
    params: list[str] = field(default_factory=list)   # nombres de parámetros (si los hay)
    param_types: list[str] = field(default_factory=list)  # tipos correspondientes a params


@dataclass
class SubProcess:
    """Un sub-proceso individual dentro de un BatchProcess."""
    name: str                       # "RESCAMPTEL", "CARTAS", "nEjecutaMotor"
    constant_value: int             # valor numérico asignado (1, 2, 3 …)
    enabled_in_xml: Optional[bool]  # None si no figura en el XML de config
    subproc_type: SubprocType

    # Clase de negocio que ejecuta este sub-proceso
    biz_namespace: str              # "BusRSProcIN"
    biz_class: str                  # "Retro"
    biz_methods: list[BizMethod] = field(default_factory=list)

    # Clase DALC asociada (si se detecta)
    dalc_class: Optional[str] = None   # "RetroDalc"

    # Texto del bloque if completo (para enriquecimiento LLM futuro)
    raw_block: str = ""


@dataclass
class BatchProcess:
    """Representa un proceso Batch completo (carpeta + XML + .cs principal)."""
    name: str                         # "RSProcIN"
    main_class: str                   # "ProcIn"
    main_cs_path: Path
    xml_config_path: Optional[Path]
    negocio_root: Path                # carpeta Negocio/ donde buscar BusXxx/

    sub_processes: list[SubProcess] = field(default_factory=list)
    xml_parameters: dict[str, str]  = field(default_factory=dict)

    # Errores no fatales durante el parsing (warnings)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_sub_processes(self) -> bool:
        return len(self.sub_processes) > 0

    @property
    def test_class_name(self) -> str:
        return f"Tests_{self.name}"
