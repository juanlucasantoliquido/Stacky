"""
schemas.technical_analysis — T2 Fase 2: schema del Análisis Técnico (TechnicalAnalyst).

Antes (Fase 1): TechnicalAnalyst.agent.md tenía una plantilla HTML inline de
~150 líneas que el LLM rellenaba. Frágil (cualquier desvío rompe el render),
imposible de validar y caro en tokens.

Ahora (Fase 2): el agente devuelve un payload JSON validado por este Pydantic
model. El sistema lo renderiza a Markdown y a HTML para ADO via
`schemas.renderer`.

Beneficio:
  - Validación contractual: ningún output llega a ADO sin las 5 secciones.
  - Anti-placeholders: el schema rechaza strings tipo "A completar".
  - Outputs uniformes y parseables (dashboards triviales).
  - Reduce ~150 líneas del prompt de TechnicalAnalyst en Fase 3.

Cubierto por tests/unit/test_technical_analysis_schema.py.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Validadores compartidos ──────────────────────────────────────────────────

PLACEHOLDER_PATTERNS = (
    re.compile(r"\bA completar\b", re.IGNORECASE),
    re.compile(r"\bTODO\b"),
    re.compile(r"\bTBD\b"),
    re.compile(r"\bpendiente\b", re.IGNORECASE),
    re.compile(r"^\s*\[(?:descripci[oó]n|nombre|valor|completar)\]\s*$", re.IGNORECASE),
    re.compile(r"Lorem ipsum", re.IGNORECASE),
)


def _no_placeholders(value: str | None, field_name: str = "field") -> str | None:
    """Rechaza strings con placeholders sin completar (cf. output_formats.md#no-placeholders)."""
    if value is None:
        return value
    for pat in PLACEHOLDER_PATTERNS:
        if pat.search(value):
            raise ValueError(
                f"{field_name}: placeholder no permitido detectado "
                f"(patrón: {pat.pattern}). "
                f"Completá con dato real o omití la sección. "
                f"Ver `Agentes/shared/output_formats.md#no-placeholders`."
            )
    return value


class _NoPlaceholderModel(BaseModel):
    """Mixin que aplica `_no_placeholders` a todos los string fields automáticamente."""

    @model_validator(mode="after")
    def _validate_no_placeholders(self):
        for name, value in self.__dict__.items():
            if isinstance(value, str):
                _no_placeholders(value, field_name=name)
        return self


# ── Sub-modelos ──────────────────────────────────────────────────────────────

class ResumenRapido(_NoPlaceholderModel):
    """Sección 0: lo mínimo para que un humano entienda el cambio en 30 segundos."""
    que_desarrollar: str = Field(..., min_length=20, description="2-3 líneas máximo, sin tecnicismos.")
    como_probar: list[str] = Field(..., min_length=1, description="Pasos concretos con datos reales si aplica.")


class FlujoPaso(_NoPlaceholderModel):
    descripcion: str = Field(..., min_length=10)
    es_cambio: bool = Field(default=False, description="Si True se renderiza con [CAMBIO] al frente.")


class TraduccionFuncionalTecnica(_NoPlaceholderModel):
    """Sección 1: requerimiento funcional → solución técnica."""
    requerimiento_funcional: str = Field(..., min_length=20)
    solucion_tecnica: str = Field(..., min_length=20)
    flujo_actual: list[FlujoPaso] = Field(..., min_length=1)
    flujo_propuesto: list[FlujoPaso] = Field(..., min_length=1)


class CambioCodigo(_NoPlaceholderModel):
    """Un cambio a nivel de método. Sin placeholders."""
    archivo: str = Field(..., pattern=r"^trunk/.+\.(?:cs|aspx|sql|md)$")
    capa: Literal["RSFac", "RSBus", "RSDalc", "AgendaWeb", "Batch", "BD", "Otro"]
    clase: str = Field(..., min_length=1)
    metodo: str = Field(..., min_length=1, description="Incluye paréntesis y params si aplica.")
    linea_aproximada: int | None = Field(default=None, ge=1)
    tipo_cambio: Literal["Agregar validación", "Modificar lógica", "Nuevo método",
                          "Eliminar código", "Refactor", "Agregar query", "Modificar query"]
    antes: str = Field(..., min_length=10)
    despues: str = Field(..., min_length=10)
    razon: str = Field(..., min_length=15)


class CambioBD(_NoPlaceholderModel):
    tipo: Literal["Campo nuevo", "Tabla nueva", "Stored procedure", "Index", "Trigger", "DDL", "DML"]
    objeto: str = Field(..., description="Ej: TABLA.CAMPO, sp_nombre, etc.")
    descripcion: str = Field(..., min_length=10)
    sql: str | None = Field(default=None, description="SQL exacto si está disponible.")


class MensajeRidioma(_NoPlaceholderModel):
    idtexto_sugerido: int = Field(..., ge=1)
    espanol: str = Field(..., min_length=1)
    portugues: str = Field(..., min_length=1)


class ArchivoAfectado(_NoPlaceholderModel):
    archivo: str = Field(..., pattern=r"^trunk/.+\.(?:cs|aspx|sql|md)$")
    capa: Literal["RSFac", "RSBus", "RSDalc", "AgendaWeb", "Batch", "BD", "Otro"]
    tipo_cambio: str


class AlcanceCambios(_NoPlaceholderModel):
    """Sección 2: archivos, métodos, BD, RIDIOMA."""
    cambios_codigo: list[CambioCodigo] = Field(..., min_length=1)
    cambios_bd: list[CambioBD] = Field(default_factory=list)
    mensajes_ridioma: list[MensajeRidioma] = Field(default_factory=list)
    archivos_afectados: list[ArchivoAfectado] = Field(..., min_length=1)


class CasoDePrueba(_NoPlaceholderModel):
    id: str = Field(..., pattern=r"^P\d{2,3}$", description="P01, P02, ...")
    descripcion: str = Field(..., min_length=10)
    datos_bd: str = Field(..., description="Datos reales: ObligID=X, ClienteID=Y, etc.")
    resultado_esperado: str = Field(..., min_length=10)


class PlanPruebasTecnico(_NoPlaceholderModel):
    """Sección 3: casos enriquecidos con datos reales de BD."""
    casos: list[CasoDePrueba] = Field(..., min_length=1)
    queries_datos_prueba: list[str] = Field(default_factory=list, description="SELECT statements para obtener datos candidatos.")
    escenarios_borde: list[str] = Field(default_factory=list)


class TestUnitario(_NoPlaceholderModel):
    """Sección 4: test unitario obligatorio."""
    id: str = Field(..., pattern=r"^TU-\d{3}$", description="TU-001, TU-002, ...")
    nombre: str = Field(..., min_length=10)
    clase_a_testear: str = Field(..., min_length=1)
    metodo_a_testear: str = Field(..., min_length=1)
    escenario: str = Field(..., min_length=10)
    setup: str = Field(..., min_length=5)
    input_params: str = Field(..., alias="input")
    expected: str = Field(..., min_length=5)
    validacion: str = Field(..., min_length=5)


class NotasDeveloper(_NoPlaceholderModel):
    """Sección 5: notas, precauciones, queries de verificación."""
    convenciones: list[str] = Field(default_factory=list)
    precauciones: list[str] = Field(default_factory=list)
    patron_referencia: str | None = Field(default=None, description="Archivo y línea de referencia si existe.")
    queries_verificacion_post: list[str] = Field(default_factory=list)


# ── Schema raíz ──────────────────────────────────────────────────────────────

class TechnicalAnalysisPayload(_NoPlaceholderModel):
    """
    Payload completo del análisis técnico que produce TechnicalAnalyst.

    Validación: 5 secciones obligatorias + metadatos. Sin placeholders.
    """
    work_item_id: int = Field(..., ge=1)
    title: str = Field(..., min_length=5)
    fecha: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    docs_consultados: list[str] = Field(default_factory=list)

    # 5 secciones obligatorias
    resumen_rapido: ResumenRapido
    traduccion: TraduccionFuncionalTecnica
    alcance: AlcanceCambios
    plan_pruebas: PlanPruebasTecnico
    tests_unitarios: list[TestUnitario] = Field(..., min_length=1)
    notas: NotasDeveloper

    @field_validator("title")
    @classmethod
    def _title_no_placeholder(cls, v: str) -> str:
        return _no_placeholders(v, "title")
