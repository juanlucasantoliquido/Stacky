"""Tests del schema TechnicalAnalysisPayload — Fase 2 / P2.6."""
import os
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from schemas import technical_analysis as _ta
from schemas.technical_analysis import TechnicalAnalysisPayload


def _payload_minimo_valido() -> dict:
    return {
        "work_item_id": 1234,
        "title": "Validar fecha vencimiento en convenios",
        "fecha": "2026-05-01",
        "docs_consultados": ["00_INDICE_MAESTRO.md", "convenios.md"],
        "resumen_rapido": {
            "que_desarrollar": "Agregar validación de fecha en ConvenioBus.GuardarConvenio() para rechazar fechas pasadas.",
            "como_probar": [
                "Abrir FrmConvenio con cliente 12345",
                "Setear fecha vencimiento al día anterior y guardar",
                "Verificar mensaje de error RIDIOMA"
            ],
        },
        "traduccion": {
            "requerimiento_funcional": "El usuario debe ser bloqueado si intenta guardar un convenio con fecha de vencimiento en el pasado.",
            "solucion_tecnica": "Agregar guard en ConvenioBus.GuardarConvenio() que verifique fechaVencimiento >= DateTime.Today.",
            "flujo_actual": [
                {"descripcion": "Usuario abre FrmConvenio", "es_cambio": False},
                {"descripcion": "Click en guardar invoca GuardarConvenio", "es_cambio": False},
                {"descripcion": "El método persiste sin validación", "es_cambio": False},
            ],
            "flujo_propuesto": [
                {"descripcion": "Usuario abre FrmConvenio", "es_cambio": False},
                {"descripcion": "Click en guardar invoca GuardarConvenio", "es_cambio": False},
                {"descripcion": "GuardarConvenio valida fecha antes de persistir", "es_cambio": True},
            ],
        },
        "alcance": {
            "cambios_codigo": [{
                "archivo": "trunk/OnLine/Negocio/RSBus/Convenio.cs",
                "capa": "RSBus",
                "clase": "Convenio",
                "metodo": "GuardarConvenio(DateTime fechaVenc)",
                "linea_aproximada": 142,
                "tipo_cambio": "Agregar validación",
                "antes": "Persistencia directa sin verificar fecha.",
                "despues": "Guard que rechaza con error RIDIOMA cuando fecha < hoy.",
                "razon": "Evita compromisos con fechas inválidas en producción.",
            }],
            "archivos_afectados": [{
                "archivo": "trunk/OnLine/Negocio/RSBus/Convenio.cs",
                "capa": "RSBus",
                "tipo_cambio": "Agregar validación",
            }],
        },
        "plan_pruebas": {
            "casos": [{
                "id": "P01",
                "descripcion": "Guardar con fecha pasada debe rechazar",
                "datos_bd": "Cliente 12345 con convenio vigente",
                "resultado_esperado": "Mensaje RIDIOMA mXXXX y registro no se persiste",
            }],
        },
        "tests_unitarios": [{
            "id": "TU-001",
            "nombre": "GuardarConvenio rechaza fecha pasada",
            "clase_a_testear": "ConvenioBus",
            "metodo_a_testear": "GuardarConvenio",
            "escenario": "Fecha vencimiento al día anterior",
            "setup": "Mock conn + fecha = ayer",
            "input": "fechaVenc = DateTime.Today.AddDays(-1)",
            "expected": "false + error en this.Errores",
            "validacion": "Assert.AreEqual(false, result) y Errores.Cantidad() > 0",
        }],
        "notas": {
            "convenciones": ["Usar Idm.Texto para el mensaje (R1)"],
            "precauciones": ["No tocar la lógica de cuotas (fuera del scope)"],
        },
    }


class TestSchemaValido:
    def test_payload_minimo_valida(self):
        p = TechnicalAnalysisPayload(**_payload_minimo_valido())
        assert p.work_item_id == 1234
        assert len(p.tests_unitarios) == 1
        assert p.alcance.cambios_codigo[0].linea_aproximada == 142

    def test_docs_consultados_default_vacio(self):
        d = _payload_minimo_valido()
        del d["docs_consultados"]
        p = TechnicalAnalysisPayload(**d)
        assert p.docs_consultados == []


class TestPlaceholdersRechazados:
    def test_a_completar_rechazado(self):
        d = _payload_minimo_valido()
        d["resumen_rapido"]["que_desarrollar"] = "A completar por el equipo más adelante."
        with pytest.raises(ValidationError) as exc:
            TechnicalAnalysisPayload(**d)
        assert "placeholder" in str(exc.value).lower()

    def test_todo_rechazado(self):
        d = _payload_minimo_valido()
        d["title"] = "TODO escribir título"
        with pytest.raises(ValidationError):
            TechnicalAnalysisPayload(**d)

    def test_lorem_ipsum_rechazado(self):
        d = _payload_minimo_valido()
        d["traduccion"]["requerimiento_funcional"] = "Lorem ipsum dolor sit amet, consectetur."
        with pytest.raises(ValidationError):
            TechnicalAnalysisPayload(**d)

    def test_descripcion_corchetes_rechazado(self):
        d = _payload_minimo_valido()
        d["alcance"]["cambios_codigo"][0]["razon"] = "[descripción]"
        with pytest.raises(ValidationError):
            TechnicalAnalysisPayload(**d)


class TestEstructura:
    def test_archivo_no_trunk_rechazado(self):
        d = _payload_minimo_valido()
        d["alcance"]["cambios_codigo"][0]["archivo"] = "OnLine/Foo.cs"  # sin prefijo trunk/
        with pytest.raises(ValidationError):
            TechnicalAnalysisPayload(**d)

    def test_test_id_invalido_rechazado(self):
        d = _payload_minimo_valido()
        d["tests_unitarios"][0]["id"] = "T-001"  # debe ser TU-NNN
        with pytest.raises(ValidationError):
            TechnicalAnalysisPayload(**d)

    def test_caso_id_invalido_rechazado(self):
        d = _payload_minimo_valido()
        d["plan_pruebas"]["casos"][0]["id"] = "Caso 1"
        with pytest.raises(ValidationError):
            TechnicalAnalysisPayload(**d)

    def test_lista_tests_unitarios_no_vacia(self):
        d = _payload_minimo_valido()
        d["tests_unitarios"] = []
        with pytest.raises(ValidationError):
            TechnicalAnalysisPayload(**d)

    def test_capa_invalida_rechazada(self):
        d = _payload_minimo_valido()
        d["alcance"]["cambios_codigo"][0]["capa"] = "RSCustom"
        with pytest.raises(ValidationError):
            TechnicalAnalysisPayload(**d)

    def test_fecha_formato_invalido_rechazada(self):
        d = _payload_minimo_valido()
        d["fecha"] = "01/05/2026"
        with pytest.raises(ValidationError):
            TechnicalAnalysisPayload(**d)
