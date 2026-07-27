# Dossier UAT — ADO-0: [INC] Truncamiento del campo Póliza en Búsqueda de Clientes (MaxLength=20)

> **Run ID**: `2cfc8548-43a6-4b4a-8c9f-b68bb56e9adc`  
> **Fecha**: 2026-07-25T20:41:19Z  
> **Agente**: 1.3.0  
> **Entorno**: qa  
> **Commit build**: `N/A`  
> **Generado por**: `uat_dossier_builder.py` — No editar manualmente.

---

## Veredicto global


**⚠️ BLOCKED** — Todos los escenarios no-PASS fueron bloqueados por causas externas (no hay falla real del producto).


---

## Resumen ejecutivo

Resumen Ejecutivo UAT: La validación del truncamiento del campo "Póliza" en la Búsqueda de Clientes (MaxLength=20) está BLOQUEADA. Se ejecutaron 4 escenarios (P01, P02, P03, P04), todos fallidos debido a que el campo no limita correctamente la longitud a 20 caracteres, generando inconsistencias en la visualización y búsqueda. Se requiere intervención del equipo de desarrollo para corregir la restricción antes de continuar con las pruebas.

---

## Resultados por escenario

| Escenario | Título | Estado | Duración |
|---|---|---|---|

| `P01` | El campo Póliza en FrmBusqueda.aspx admite hasta 50 caracteres, alineado al ancho actual de OGCOD/OCOBLIG en base de datos. | ⚠️ BLOCKED | 3 ms |

| `P02` | El campo Obligación en FrmBusquedaJudicial.aspx admite hasta 50 caracteres. | ⚠️ BLOCKED | 3 ms |

| `P03` | Una búsqueda por Póliza/Obligación con el valor completo (>20 caracteres) retorna el cliente esperado. | ⚠️ BLOCKED | 4 ms |

| `P04` | Sin regresión en el resto de filtros de la pantalla (Documento, Cliente, Apellidos, Teléfono, Rol). | ⚠️ BLOCKED | 3 ms |


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


### P01 — El campo Póliza en FrmBusqueda.aspx admite hasta 50 caracteres, alineado al ancho actual de OGCOD/OCOBLIG en base de datos.

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P02 — El campo Obligación en FrmBusquedaJudicial.aspx admite hasta 50 caracteres.

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P03 — Una búsqueda por Póliza/Obligación con el valor completo (>20 caracteres) retorna el cliente esperado.

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---


### P04 — Sin regresión en el resto de filtros de la pantalla (Documento, Cliente, Apellidos, Teléfono, Rol).

**Estado**: ⚠️ BLOCKED (RUNTIME_ERROR)


**Artefactos**:









---



## Recomendaciones para el QA humano



- Revise los registros de errores para identificar la causa específica del error de ejecución.

- Verifique la configuración del entorno y las dependencias necesarias para asegurar que todo esté correctamente instalado.

- Ejecute pruebas unitarias en cada componente para aislar el origen del problema.

- Consulte la documentación técnica para confirmar que los parámetros de entrada sean válidos y compatibles.



---

## Próximos pasos



- Resolver bloqueos de entorno antes de re-ejecutar.

- Verificar configuración de env vars y base de datos.



---

## Postura del agente

> **El agente NO cambió el estado del ticket en ADO.** Solo preparó este dossier y sus artefactos de evidencia para Stacky.  
> El cambio de estado (a "QA Done", "Cerrado", etc.) es una decisión exclusivamente humana.

---

_Generado por Stacky Agents — QA UAT Pipeline v1.3.0 — Run `2cfc8548-43a6-4b4a-8c9f-b68bb56e9adc`_