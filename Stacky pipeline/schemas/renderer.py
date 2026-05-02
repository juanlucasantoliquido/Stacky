"""
schemas.renderer — T2 Fase 2: convierte payloads JSON a Markdown / HTML para ADO.

Recibe un `TechnicalAnalysisPayload` validado y produce:
  - Markdown limpio para el repo / dashboards.
  - HTML compatible con ADO (vía `ado_html_postprocessor.py` o directo).

Orden de las secciones reproduce la plantilla histórica de TechnicalAnalyst,
para que el cambio sea drop-in (mismo output visual, distinto pipeline).
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from schemas.technical_analysis import TechnicalAnalysisPayload  # noqa: E402


def render_md(payload: TechnicalAnalysisPayload) -> str:
    """Renderiza el payload a Markdown."""
    parts: list[str] = []
    parts.append(f"## ANÁLISIS TÉCNICO — ADO-{payload.work_item_id}")
    parts.append("")
    parts.append("> Generado por: Analista Técnico Agéntico  ")
    parts.append(f"> Fecha: {payload.fecha}  ")
    if payload.docs_consultados:
        parts.append(f"> Documentación consultada: {', '.join(payload.docs_consultados)}")
    parts.append("")
    parts.append("---")
    parts.append("")

    # Sección 0
    parts.append("## 0. RESUMEN RÁPIDO")
    parts.append("")
    parts.append("### Qué debe desarrollar el Developer")
    parts.append(payload.resumen_rapido.que_desarrollar)
    parts.append("")
    parts.append("### Cómo probar (paso a paso)")
    for i, paso in enumerate(payload.resumen_rapido.como_probar, 1):
        parts.append(f"{i}. {paso}")
    parts.append("")
    parts.append("---")
    parts.append("")

    # Sección 1
    parts.append("## 1. TRADUCCIÓN FUNCIONAL → TÉCNICA")
    parts.append("")
    parts.append("### Requerimiento funcional (resumen)")
    parts.append(payload.traduccion.requerimiento_funcional)
    parts.append("")
    parts.append("### Solución técnica propuesta")
    parts.append(payload.traduccion.solucion_tecnica)
    parts.append("")
    parts.append("### Flujo actual del sistema (cómo funciona HOY)")
    for i, paso in enumerate(payload.traduccion.flujo_actual, 1):
        parts.append(f"{i}. {paso.descripcion}")
    parts.append("")
    parts.append("### Flujo propuesto (cómo debe funcionar DESPUÉS)")
    for i, paso in enumerate(payload.traduccion.flujo_propuesto, 1):
        prefix = "**[CAMBIO]** " if paso.es_cambio else ""
        parts.append(f"{i}. {prefix}{paso.descripcion}")
    parts.append("")
    parts.append("---")
    parts.append("")

    # Sección 2
    parts.append("## 2. ALCANCE DE CAMBIOS")
    parts.append("")
    parts.append("### Cambios en código — nivel de método")
    parts.append("")
    for c in payload.alcance.cambios_codigo:
        linea = f" — línea ~{c.linea_aproximada}" if c.linea_aproximada else ""
        parts.append(f"#### `{c.archivo}` ({c.capa})")
        parts.append(f"**Clase:** `{c.clase}`  ")
        parts.append(f"**Método:** `{c.metodo}`{linea}  ")
        parts.append(f"**Tipo de cambio:** {c.tipo_cambio}")
        parts.append("")
        parts.append(f"- **Antes:** {c.antes}")
        parts.append(f"- **Después:** {c.despues}")
        parts.append(f"- **Razón:** {c.razon}")
        parts.append("")

    if payload.alcance.cambios_bd:
        parts.append("### Cambios en base de datos")
        parts.append("")
        parts.append("| Tipo | Objeto | Descripción |")
        parts.append("|---|---|---|")
        for cb in payload.alcance.cambios_bd:
            parts.append(f"| {cb.tipo} | `{cb.objeto}` | {cb.descripcion} |")
        parts.append("")
        for cb in payload.alcance.cambios_bd:
            if cb.sql:
                parts.append(f"```sql")
                parts.append(cb.sql)
                parts.append("```")
                parts.append("")

    if payload.alcance.mensajes_ridioma:
        parts.append("### RIDIOMA — mensajes nuevos")
        parts.append("")
        parts.append("| IDTEXTO | Español | Portugués |")
        parts.append("|---|---|---|")
        for m in payload.alcance.mensajes_ridioma:
            parts.append(f"| {m.idtexto_sugerido} | {m.espanol} | {m.portugues} |")
        parts.append("")

    parts.append("### Archivos afectados — resumen")
    parts.append("")
    parts.append("| Archivo | Capa | Tipo de cambio |")
    parts.append("|---|---|---|")
    for a in payload.alcance.archivos_afectados:
        parts.append(f"| `{a.archivo}` | {a.capa} | {a.tipo_cambio} |")
    parts.append("")
    parts.append("---")
    parts.append("")

    # Sección 3
    parts.append("## 3. PLAN DE PRUEBAS TÉCNICO")
    parts.append("")
    parts.append("### Pruebas funcionales enriquecidas con datos reales")
    parts.append("")
    parts.append("| # | Caso | Datos BD | Resultado esperado |")
    parts.append("|---|---|---|---|")
    for caso in payload.plan_pruebas.casos:
        parts.append(f"| {caso.id} | {caso.descripcion} | {caso.datos_bd} | {caso.resultado_esperado} |")
    parts.append("")

    if payload.plan_pruebas.queries_datos_prueba:
        parts.append("### Queries para obtener datos de prueba")
        parts.append("")
        for q in payload.plan_pruebas.queries_datos_prueba:
            parts.append("```sql")
            parts.append(q)
            parts.append("```")
            parts.append("")

    if payload.plan_pruebas.escenarios_borde:
        parts.append("### Escenarios de borde")
        parts.append("")
        for e in payload.plan_pruebas.escenarios_borde:
            parts.append(f"- {e}")
        parts.append("")

    parts.append("---")
    parts.append("")

    # Sección 4
    parts.append("## 4. TESTS UNITARIOS OBLIGATORIOS")
    parts.append("")
    parts.append("> Todos los tests deben pasar al 100% antes de dar por completado el desarrollo.")
    parts.append("")
    for t in payload.tests_unitarios:
        parts.append(f"### {t.id}: {t.nombre}")
        parts.append("")
        parts.append(f"- **Clase a testear:** `{t.clase_a_testear}`")
        parts.append(f"- **Método:** `{t.metodo_a_testear}`")
        parts.append(f"- **Escenario:** {t.escenario}")
        parts.append(f"- **Setup:** {t.setup}")
        parts.append(f"- **Input:** {t.input_params}")
        parts.append(f"- **Expected:** {t.expected}")
        parts.append(f"- **Validación:** {t.validacion}")
        parts.append("")

    parts.append("---")
    parts.append("")

    # Sección 5
    parts.append("## 5. NOTAS PARA EL DESARROLLADOR")
    parts.append("")
    if payload.notas.convenciones:
        parts.append("### Convenciones a respetar")
        for c in payload.notas.convenciones:
            parts.append(f"- {c}")
        parts.append("")
    if payload.notas.precauciones:
        parts.append("### Precauciones")
        for p in payload.notas.precauciones:
            parts.append(f"- {p}")
        parts.append("")
    if payload.notas.patron_referencia:
        parts.append("### Patrón de referencia en el proyecto")
        parts.append(payload.notas.patron_referencia)
        parts.append("")
    if payload.notas.queries_verificacion_post:
        parts.append("### Queries de verificación post-implementación")
        parts.append("")
        for q in payload.notas.queries_verificacion_post:
            parts.append("```sql")
            parts.append(q)
            parts.append("```")
            parts.append("")

    parts.append("---")
    parts.append("")
    parts.append(f"**Próximo paso:** Desarrollador toma este ticket e implementa siguiendo este análisis.")

    return "\n".join(parts)


def render_html_for_ado(payload: TechnicalAnalysisPayload) -> str:
    """
    Renderiza a HTML compatible con ADO via `ado_html_postprocessor`.
    Usa el render Markdown como input.
    """
    from ado_html_postprocessor import md_to_ado_html
    md = render_md(payload)
    return md_to_ado_html(md)
