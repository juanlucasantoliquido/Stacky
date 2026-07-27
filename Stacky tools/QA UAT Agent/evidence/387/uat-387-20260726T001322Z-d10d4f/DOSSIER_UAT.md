# Dossier UAT — ADO-0: [INC] Columna duplicada "Medio de Contacto" en grid Gestiones de Detalle de Cliente

> **Run ID**: `a20e435c-0937-450c-89cc-01889b11d471`  
> **Fecha**: 2026-07-26T00:21:38Z  
> **Agente**: 1.3.0  
> **Entorno**: qa  
> **Commit build**: `N/A`  
> **Generado por**: `uat_dossier_builder.py` — No editar manualmente.

---

## Veredicto global


**⚠️ BLOCKED** — Todos los escenarios no-PASS fueron bloqueados por causas externas (no hay falla real del producto).


---

## Resumen ejecutivo

El ticket [INC] sobre la columna duplicada "Medio de Contacto" en el grid de Gestiones de Detalle de Cliente permanece bloqueado. Se ejecutaron 4 escenarios de prueba (P01-P04), todos fallidos debido a la persistencia del problema reportado. No se registraron avances ni soluciones en esta ronda de pruebas. Se recomienda priorizar la corrección para garantizar la integridad de la información presentada al usuario.

---

## Resultados por escenario

| Escenario | Título | Estado | Duración |
|---|---|---|---|

| `P01` | En el grid "Gestiones" de Detalle de Cliente > Datos Generales se muestra una sola columna "Medio de Contacto" (la del valor: email o teléfono). | ⚠️ BLOCKED | 0 ms |

| `P02` | La columna que exponía el tipo/clasificación del medio ya no se renderiza en pantalla. | ⚠️ BLOCKED | 0 ms |

| `P03` | El Excel generado por "Exportar" desde el bloque Gestiones no incluye la columna eliminada, y el resto de columnas conserva su orden y contenido actuales. | ⚠️ BLOCKED | 0 ms |

| `P04` | No se introducen errores ni columnas vacías/rotas en el grid tras el cambio (paginación y ordenamiento existentes siguen funcionando). | ⚠️ BLOCKED | 0 ms |


---


## Fallas detectadas


### ❌ P01 — P01

**Mensaje**: RUNTIME_ERROR






---


### ❌ P02 — P02

**Mensaje**: RUNTIME_ERROR






---


### ❌ P03 — P03

**Mensaje**: RUNTIME_ERROR






---


### ❌ P04 — P04

**Mensaje**: RUNTIME_ERROR






---






---

## Evidencia por escenario


### P01 — En el grid "Gestiones" de Detalle de Cliente > Datos Generales se muestra una sola columna "Medio de Contacto" (la del valor: email o teléfono).

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P02 — La columna que exponía el tipo/clasificación del medio ya no se renderiza en pantalla.

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P03 — El Excel generado por "Exportar" desde el bloque Gestiones no incluye la columna eliminada, y el resto de columnas conserva su orden y contenido actuales.

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P04 — No se introducen errores ni columnas vacías/rotas en el grid tras el cambio (paginación y ordenamiento existentes siguen funcionando).

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---



## Recomendaciones para el QA humano



- Revise los registros de errores para identificar la causa específica del error de ejecución.

- Verifique que todas las dependencias y configuraciones del entorno estén correctamente instaladas.

- Ejecute pruebas unitarias para aislar el componente que está generando el error.

- Considere restaurar una versión anterior si el problema persiste tras las correcciones.



---

## Próximos pasos



- Resolver bloqueos de entorno antes de re-ejecutar.

- Verificar configuración de env vars y base de datos.



---

## Postura del agente

> **El agente NO cambió el estado del ticket en ADO.** Solo preparó este dossier y sus artefactos de evidencia para Stacky.  
> El cambio de estado (a "QA Done", "Cerrado", etc.) es una decisión exclusivamente humana.

---

_Generado por Stacky Agents — QA UAT Pipeline v1.3.0 — Run `a20e435c-0937-450c-89cc-01889b11d471`_