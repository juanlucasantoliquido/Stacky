"""Tests del renderer JSON → Markdown / HTML — Fase 2 / P2.6."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from schemas.technical_analysis import TechnicalAnalysisPayload
from schemas.renderer import render_md, render_html_for_ado


def _payload_completo() -> TechnicalAnalysisPayload:
    """Construye un payload válido y completo (todas las secciones populadas)."""
    return TechnicalAnalysisPayload(
        work_item_id=1234,
        title="Validar fecha vencimiento en convenios",
        fecha="2026-05-01",
        docs_consultados=["00_INDICE_MAESTRO.md"],
        resumen_rapido={
            "que_desarrollar": "Agregar validación de fecha en ConvenioBus.GuardarConvenio().",
            "como_probar": ["Abrir FrmConvenio", "Setear fecha pasada", "Verificar error"],
        },
        traduccion={
            "requerimiento_funcional": "Bloquear fechas pasadas al guardar convenio.",
            "solucion_tecnica": "Guard en GuardarConvenio() que rechaza fechas < hoy.",
            "flujo_actual": [{"descripcion": "Usuario guarda sin validación", "es_cambio": False}],
            "flujo_propuesto": [{"descripcion": "Usuario guarda con validación de fecha", "es_cambio": True}],
        },
        alcance={
            "cambios_codigo": [{
                "archivo": "trunk/OnLine/Negocio/RSBus/Convenio.cs",
                "capa": "RSBus",
                "clase": "Convenio",
                "metodo": "GuardarConvenio(DateTime fechaVenc)",
                "linea_aproximada": 142,
                "tipo_cambio": "Agregar validación",
                "antes": "Persistencia directa sin verificar fecha.",
                "despues": "Guard que rechaza fechas pasadas.",
                "razon": "Evitar compromisos inválidos.",
            }],
            "cambios_bd": [{
                "tipo": "Campo nuevo",
                "objeto": "RCONVP.FECHA_VALIDACION",
                "descripcion": "Timestamp de cuándo se validó.",
                "sql": "ALTER TABLE RCONVP ADD FECHA_VALIDACION DATE NULL;",
            }],
            "mensajes_ridioma": [{
                "idtexto_sugerido": 5001,
                "espanol": "Fecha de vencimiento debe ser futura",
                "portugues": "Data de vencimento deve ser futura",
            }],
            "archivos_afectados": [{
                "archivo": "trunk/OnLine/Negocio/RSBus/Convenio.cs",
                "capa": "RSBus",
                "tipo_cambio": "Agregar validación",
            }],
        },
        plan_pruebas={
            "casos": [{
                "id": "P01",
                "descripcion": "Guardar con fecha pasada",
                "datos_bd": "Cliente 12345",
                "resultado_esperado": "Error RIDIOMA, sin persistir",
            }],
            "queries_datos_prueba": ["SELECT TOP 5 CLCOD FROM RCLIE WHERE CLEMPRESA='01';"],
            "escenarios_borde": ["Fecha = hoy mismo (no pasada, no futura)"],
        },
        tests_unitarios=[{
            "id": "TU-001",
            "nombre": "GuardarConvenio rechaza fecha pasada",
            "clase_a_testear": "ConvenioBus",
            "metodo_a_testear": "GuardarConvenio",
            "escenario": "Fecha al día anterior",
            "setup": "Mock conn + fecha = ayer",
            "input": "fechaVenc = ayer",
            "expected": "false + error",
            "validacion": "Assert false y errores > 0",
        }],
        notas={
            "convenciones": ["Usar Idm.Texto (R1)"],
            "precauciones": ["No tocar lógica de cuotas"],
            "patron_referencia": "Ver Cliente.cs:GuardarCliente() línea 89.",
            "queries_verificacion_post": ["SELECT * FROM RCONVP WHERE FECHA_VALIDACION IS NOT NULL;"],
        },
    )


class TestMarkdownRender:
    def test_contiene_todas_las_secciones(self):
        md = render_md(_payload_completo())
        assert "## ANÁLISIS TÉCNICO — ADO-1234" in md
        assert "## 0. RESUMEN RÁPIDO" in md
        assert "## 1. TRADUCCIÓN FUNCIONAL → TÉCNICA" in md
        assert "## 2. ALCANCE DE CAMBIOS" in md
        assert "## 3. PLAN DE PRUEBAS TÉCNICO" in md
        assert "## 4. TESTS UNITARIOS OBLIGATORIOS" in md
        assert "## 5. NOTAS PARA EL DESARROLLADOR" in md

    def test_resumen_rapido_lista_pasos(self):
        md = render_md(_payload_completo())
        assert "1. Abrir FrmConvenio" in md
        assert "2. Setear fecha pasada" in md
        assert "3. Verificar error" in md

    def test_flujo_propuesto_marca_cambios(self):
        md = render_md(_payload_completo())
        assert "**[CAMBIO]**" in md

    def test_archivo_y_capa_renderizado(self):
        md = render_md(_payload_completo())
        assert "`trunk/OnLine/Negocio/RSBus/Convenio.cs`" in md
        assert "RSBus" in md

    def test_metodo_y_linea_renderizado(self):
        md = render_md(_payload_completo())
        assert "`GuardarConvenio(DateTime fechaVenc)`" in md
        assert "línea ~142" in md

    def test_cambio_bd_con_sql(self):
        md = render_md(_payload_completo())
        assert "ALTER TABLE RCONVP ADD FECHA_VALIDACION" in md
        assert "```sql" in md

    def test_ridioma_tabla(self):
        md = render_md(_payload_completo())
        assert "5001" in md
        assert "Fecha de vencimiento debe ser futura" in md

    def test_test_unitario_renderizado(self):
        md = render_md(_payload_completo())
        assert "### TU-001:" in md
        assert "ConvenioBus" in md
        assert "Assert false y errores > 0" in md

    def test_notas_secciones(self):
        md = render_md(_payload_completo())
        assert "Convenciones a respetar" in md
        assert "Usar Idm.Texto" in md
        assert "No tocar lógica de cuotas" in md


class TestHtmlRender:
    def test_html_para_ado_genera_tags(self):
        html = render_html_for_ado(_payload_completo())
        # Debe tener tags HTML, no Markdown crudo
        assert "<h2>" in html
        assert "<table" in html
        assert "##" not in html or html.count("##") == 0  # no markdown raw

    def test_html_tabla_con_styles_inline(self):
        html = render_html_for_ado(_payload_completo())
        # ado_html_postprocessor debe haber inyectado styles inline
        assert "border-collapse:collapse" in html


class TestEmptyOptionals:
    def test_render_funciona_sin_cambios_bd(self):
        from schemas.technical_analysis import TechnicalAnalysisPayload
        p = _payload_completo()
        # Quitar cambios BD
        d = p.model_dump()
        d["alcance"]["cambios_bd"] = []
        d["alcance"]["mensajes_ridioma"] = []
        d["tests_unitarios"][0].pop("input_params", None)
        d["tests_unitarios"][0].setdefault("input", "fechaVenc = ayer")
        p2 = TechnicalAnalysisPayload(**d)
        md = render_md(p2)
        assert "## 2. ALCANCE DE CAMBIOS" in md
        # Sección de cambios BD ausente
        assert "Cambios en base de datos" not in md
