---
tipo: incidencia
incident_id: inc_20260717_175135_fa6e21
execution_id: 97
tracker_id: 
work_item_type: Issue
epica: 
estado: analizada
fecha: 2026-07-17
origen: stacky-incident-resolver
---

# INC- — [INC] Prestamos por Obligación: Resumen vacío y cuotas sin ordenar por fecha de vencimiento

> Issue:  · Sin épica relacionada

<h1>[INC] Prestamos por Obligación: Resumen vacío y cuotas sin ordenar por fecha de vencimiento</h1>

<h2>RESUMEN EJECUTIVO</h2>
<p>
Al abrir el diálogo de Prestamos por Obligación en el Detalle de Cliente (caso de prueba CP-DET-ADD-05),
los campos de resumen superior —Obligación, Capital Inicial, Total de Cuotas, Cuotas Vencidas,
Cuotas Venc. Impagas y Cuotas No Vencidas— aparecen en blanco aunque la grilla inferior
muestra las cuotas con datos. Además, la grilla ordena las filas de forma ascendente por CUFECVTO
en lugar de descendente (del más reciente al más antiguo). Impacta a los gestores de cobranza
que necesitan el resumen de la obligación al momento de la negociación. Severidad: media.
</p>

<h2>CONTEXTO DE NEGOCIO</h2>
<p>
El módulo Detalle de Cliente permite al gestor consultar el estado de las obligaciones de un deudor.
Al hacer clic en una obligación tipo Préstamo (TipoAnalitico = "1"), se abre el diálogo
<em>dlgPrestamos</em> que debe mostrar un resumen cabecera (obligación, capital inicial, conteo de cuotas)
y la grilla de cuotas. El gestor utiliza esos datos para evaluar la mora y negociar un compromiso de pago.
Sin el resumen, el gestor opera a ciegas respecto al capital original y la distribución de cuotas vencidas,
lo que compromete la calidad de la gestión y la trazabilidad de la incidencia durante UAT.
</p>

<h2>ANALISIS FUNCIONAL</h2>
<p>
<strong>Comportamiento esperado:</strong><br/>
— Sección "Detalle Cuota": campo Obligación muestra el código de la obligación.<br/>
— Sección "Totales": campo Capital Inicial muestra el monto formateado.<br/>
— Sección "Cuotas": Total de Cuotas, Cuotas Vencidas, Cuotas Venc. Impagas y Cuotas No Vencidas muestran sus valores enteros.<br/>
— Grilla Cuotas: filas ordenadas por FECHA VENC. en forma <em>descendente</em> (más reciente primero).
</p>
<p>
<strong>Comportamiento observado (captura CP-DET-ADD-05):</strong><br/>
— Los cuatro campos del resumen aparecen como etiquetas vacías sin valor asociado.<br/>
— La grilla muestra 3 cuotas con CUFECVTO 31/03/2026, 15/03/2026, 31/03/2026 (orden ascendente, no descendente).
</p>
<p>
<strong>Casos borde:</strong><br/>
— Obligación sin registro en RPRES: suma 0 de cuotas, todos los contadores en 0.<br/>
— Cuotas con misma CUFECVTO: secundar el orden por CUNROCUOT descendente.<br/>
— Campo abfFrecuenciaDevengacion (Cuotas No Vencidas) declarado con FieldDataType="EnteroNegativo": verificar que no bloquee el renderizado cuando el valor calculado es 0.
</p>
<p>
<strong>Plan de pruebas mínimo:</strong><br/>
1. Abrir Detalle de Cliente, seleccionar una obligación de tipo Préstamo (TipoAnalitico=1) y verificar que los 6 campos de resumen muestren valores.<br/>
2. Verificar que la grilla esté ordenada de mayor a menor FECHA VENC.<br/>
3. Confirmar con una obligación que tenga cuotas de igual fecha que el segundo criterio de ordenamiento funcione.<br/>
4. Verificar la obligación del caso CP-DET-ADD-05 específicamente.
</p>

<h2>ANALISIS TECNICO</h2>
<p>
<strong>Defecto 1 — Resumen vacío:</strong><br/>
<code>getDatosCabecerPrestamo</code> (RSDalc/Obligaciones.cs:630) ejecuta un
<code>INNER JOIN RPRES INNER JOIN ROBLG ON OGCOD = PROBLIG</code>.
Si la obligación no tiene registro en la tabla RPRES, la consulta retorna 0 filas.
El code-behind guarda el guard <code>if (Ds.Tables["DATPRES"].Rows.Count &gt; 0)</code>
(FrmDetalleClie.aspx.cs:2980), por lo que ningún campo se asigna y todos quedan en blanco.
La grilla de cuotas se carga desde un segundo método (<code>getCuotasOblig</code>:2012)
que consulta RCUOTAS directamente, independiente de RPRES, razón por la que la grilla sí muestra datos.
<strong>Hipótesis principal:</strong> la obligación del test no tiene fila en RPRES
(posible gap en la carga IncHost o Mul2Bane para este tipo de producto).
<strong>Hipótesis alternativa:</strong> el código de obligación pasado difiere de PROBLIG
(diferencia de padding/tipo de dato entre OGCOD y PROBLIG).
</p>
<p>
<strong>Defecto 2 — Ordenamiento ascendente:</strong><br/>
<code>getCuotasOblig</code> (RSDalc/Obligaciones.cs:682) usa
<code>ORDER BY CUNROCUOT +1-1, CUFECVTO</code> (orden ascendente en ambas columnas).
El fix es cambiar a <code>ORDER BY CUFECVTO DESC</code>; si se quiere sub-ordenamiento
por número de cuota: <code>ORDER BY CUFECVTO DESC, CUNROCUOT DESC</code>.
</p>
<p>
<strong>Approach de fix:</strong><br/>
1. Verificar existencia del registro en RPRES para la obligación del test: si falta, escalar al equipo de Batch/carga.<br/>
2. Si RPRES sí tiene datos para otras obligaciones del mismo tipo, comparar tipos/padding de OGCOD vs PROBLIG.<br/>
3. En todo caso, cambiar la cláusula ORDER BY en <code>getCuotasOblig</code>.<br/>
4. Evaluar si el FieldDataType="EnteroNegativo" de abfFrecuenciaDevengacion puede causar problema visual cuando el valor es ≥ 0 y corregirlo a "Entero".
</p>

<h2>PASOS DE REPRODUCCION</h2>
<ol>
  <li>Ingresar a AgendaWeb y abrir el Detalle de Cliente del deudor afectado.</li>
  <li>Navegar a la solapa/sección de Obligaciones.</li>
  <li>Hacer clic en una obligación de tipo Préstamo (TipoAnalitico = "1") para abrir el diálogo Prestamos.</li>
  <li>Observar que los campos Obligación, Capital Inicial, Total de Cuotas, Cuotas Vencidas, Cuotas Venc. Impagas y Cuotas No Vencidas aparecen vacíos.</li>
  <li>Observar el orden de las filas en la grilla Cuotas: verificar que NO están en orden descendente por Fecha Venc.</li>
</ol>

<h2>CRITERIOS DE ACEPTACION</h2>
<ul>
  <li>El campo "Obligación" en Detalle Cuota muestra el código de la obligación (PROBLIG) o " -- " si está vacío.</li>
  <li>El campo "Capital Inicial" en Totales muestra el monto formateado (PRCAPINI).</li>
  <li>Los campos Total de Cuotas, Cuotas Vencidas, Cuotas Venc. Impagas y Cuotas No Vencidas muestran sus valores numéricos enteros ≥ 0.</li>
  <li>Las filas de la grilla Cuotas están ordenadas de mayor a menor por Fecha Venc. (CUFECVTO DESC).</li>
  <li>En caso de empate en CUFECVTO, las cuotas se ordenan por CUNROCUOT de mayor a menor.</li>
  <li>El comportamiento es consistente en AgendaWeb y AutoGestión (ambos FrmDetalleClie).</li>
</ul>

<h2>ARCHIVOS Y MODULOS PROBABLES</h2>
<ul>
  <li>trunk/OnLine/Negocio/RSDalc/Obligaciones.cs:661 — <code>getCuotasOblig</code>: corregir ORDER BY a CUFECVTO DESC</li>
  <li>trunk/OnLine/Negocio/RSDalc/Obligaciones.cs:630 — <code>getDatosCabecerPrestamo</code>: investigar por qué no retorna filas para la obligación del test (INNER JOIN con RPRES)</li>
  <li>trunk/OnLine/AgendaWeb/FrmDetalleClie.aspx.cs:2969 — <code>CargoDatosModalPrestamos</code>: guard condicional Rows.Count &gt; 0, evaluar comportamiento cuando DATPRES está vacío</li>
  <li>trunk/OnLine/AgendaWeb/FrmDetalleClie.aspx:669 — abfFrecuenciaDevengacion declarado con FieldDataType="EnteroNegativo" — verificar si impide render cuando valor ≥ 0</li>
  <li>trunk/OnLine/AutoGestion/FrmDetalleClie.aspx.cs — mismo método: verificar paridad con AgendaWeb</li>
</ul>

<h2>EPICA RELACIONADA</h2>
<p>EPICA: 316 | CONFIANZA: 88 | RAZON: EP-48 "Ajuste Visual y Funcional en Detalle de Cuotas de Obligación" cubre directamente la visualización y funcionalidad del diálogo de cuotas de una obligación (dlgPrestamos), que es exactamente el componente afectado por ambos defectos</p>

<h2>PRIORIDAD Y ESTIMACION</h2>
<p>Prioridad: media. Estimación: S. La incidencia fue detectada en UAT (CP-DET-ADD-05) y aún no está en producción. El fix del ordenamiento es un cambio de una línea en SQL (ORDER BY). El fix del resumen vacío puede requerir investigación de datos en RPRES; si es un gap de datos de test el esfuerzo es mínimo, si es un defecto de lógica de JOIN puede subir a M.</p>

## Relacionados

- [[INDICE_INCIDENCIAS]]
- Archivos probables (aristas a código):
trunk/OnLine/Negocio/RSDalc/Obligaciones.cs:661
trunk/OnLine/Negocio/RSDalc/Obligaciones.cs:630
trunk/OnLine/AgendaWeb/FrmDetalleClie.aspx.cs:2969
trunk/OnLine/AgendaWeb/FrmDetalleClie.aspx:669
trunk/OnLine/AutoGestion/FrmDetalleClie.aspx.cs
